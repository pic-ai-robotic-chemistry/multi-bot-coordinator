import collections
import sqlite3
from docplex.cp.model import *
from pprint import pprint
from utils.db_tools import *

def fespb(cur_ptr, conn_sql: sqlite3.Connection, time_limit=120):

    jobs_data = construct_fjspb_jobs_data_from_db(conn_sql)

    machines_list = []
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, _, _) in enumerate(job):
            for m_id in machines:
                if m_id not in machines_list:
                    machines_list.append(m_id)

    batch_capacities = {}
    for code in machines_list:
        batch_capacities[code] = find_capacity_by_ws_code_from_db(code, conn_sql)

    # pprint(jobs_data)
    # pprint(machines_list)
    # pprint(batch_capacities)

    # Parameters

    horizon = sum(task[1] for job_id, job in jobs_data.items() for task in job)

    # Create model
    mdl = CpoModel(name="FlexibleJobShopBatch")
    # ['Quiet', 'Terse', 'Normal', 'Verbose']
    mdl.set_parameters(CpoParameters(LogVerbosity="Quiet", WarningLevel=1, TimeLimit=time_limit))

    # Decision variables, including the interval for each task and the interval for S2M
    all_tasks = {}
    # S2M
    task_to_machine = collections.defaultdict(dict)
    # For each machine's tasks, they are not needed now but will be used in the Synchronizing step
    machine_to_intervals = collections.defaultdict(list)
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, _, sche_info_dict) in enumerate(job):
            # Simulation: Used for simulation and plotting of tasks inserted midway
            if sche_info_dict["start_time"] is not None and sche_info_dict["start_time"] < cur_ptr:
                # If it has already been scheduled
                # if sche_info_dict["has_scheduled"] is not None and sche_info_dict["has_scheduled"] == True:
                all_tasks[job_id, task_id] = interval_var(
                    start=sche_info_dict["start_time"], end=sche_info_dict["end"]
                )
            # If it has not been scheduled yet
            else:
                all_tasks[job_id, task_id] = interval_var(start=[0, horizon], end=[0, horizon])
            for m_id in machines:
                task_to_machine[job_id, task_id][m_id] = interval_var(
                    size=[duration, duration],
                    optional=True,
                    name="B{}-T{}-M{}-D{}".format(job_id, task_id, m_id, duration),
                )
                machine_to_intervals[m_id].append(task_to_machine[job_id, task_id][m_id])

    # Routing: Ensure that each task can be assigned to only one machine
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, _, _) in enumerate(job):
            mdl.add(
                alternative(
                    all_tasks[job_id, task_id],
                    [task_to_machine[job_id, task_id][m_id] for m_id in machines],
                )
            )

    # Sequencing: Ensure priority constraints for tasks within each job
    for job_id, job in jobs_data.items():
        for task_id in range(len(job) - 1):
            mdl.add(end_before_start(all_tasks[job_id, task_id], all_tasks[job_id, task_id + 1]))

    # Synchronizing
    state = {m_id: state_function(name="machine_" + str(m_id)) for m_id in machines_list}
    for index, m_id in enumerate(machines_list):
        for itv in machine_to_intervals[m_id]:
            mdl.add(always_equal(state[m_id], itv, index, isStartAligned=True, isEndAligned=True))

    # Batching: A batch must not exceed the capacity of the batch-processing machine
    batch_usage = {m_id: step_at(0, 0) for m_id in machines_list}
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, _, _) in enumerate(job):
            for m_id in machines:
                batch_usage[m_id] += pulse(task_to_machine[job_id, task_id][m_id], 1)
    for m_id in machines_list:
        mdl.add(batch_usage[m_id] <= batch_capacities[m_id])

    # ----------------------------------Constraints for electrochemical and XRD processes------------------------------
    test_machine_schedule = {}
    dripping_machine_schedule = {}
    recycle_machine_schedule = {}
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, _, _) in enumerate(job):
            for m_id in machines:
                if "test" in m_id:
                    test_machine_schedule[(job_id, task_id)] = all_tasks[job_id, task_id]
                elif "dripping" in m_id:
                    dripping_machine_schedule[(job_id, task_id)] = all_tasks[job_id, task_id]
                elif "recycle" in m_id:
                    recycle_machine_schedule[(job_id, task_id)] = all_tasks[job_id, task_id]
    for task_dripping in dripping_machine_schedule.values():
        for task_test in test_machine_schedule.values():
            mdl.add(overlap_length(task_dripping, task_test) == 0)
            for task_recycle in recycle_machine_schedule.values():
                mdl.add(overlap_length(task_test, task_recycle) == 0)
                mdl.add(overlap_length(task_dripping, task_recycle) == 0)
    for index, job_id in enumerate(list(jobs_data.keys())):
        for task_id, (machines, duration, _, _) in enumerate(jobs_data[job_id]):
            for m_id in machines:
                if "dripping" in m_id:
                    mdl.add(end_at_start(all_tasks[job_id, task_id], all_tasks[job_id, task_id + 1]))
                    mdl.add(end_at_start(all_tasks[job_id, task_id + 1], all_tasks[job_id, task_id + 2]))
    # -------------------------------------------------------------------------------------
    # -----------------------muffle furnace----------------------------------
    muffle_furnace_temp_dict = defaultdict(lambda: defaultdict(list))
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, parameters, _) in enumerate(job):
            for m_id in machines:
                if "muffle_furnace" in m_id:
                    temperature = json.loads(parameters[0]["param"]["custom_param"])["temperature"]
                    muffle_furnace_temp_dict[m_id][temperature].append(all_tasks[job_id, task_id])
    for m_id in muffle_furnace_temp_dict.keys():
        temperatures = list(muffle_furnace_temp_dict[m_id].keys())
        for i in range(len(temperatures)):
            for j in range(i + 1, len(temperatures)):
                temp1 = temperatures[i]
                temp2 = temperatures[j]
                itvs_temp1 = muffle_furnace_temp_dict[m_id][temp1]
                itvs_temp2 = muffle_furnace_temp_dict[m_id][temp2]
                for itv_temp1 in itvs_temp1:
                    for itv_temp2 in itvs_temp2:
                        mdl.add(overlap_length(itv_temp1, itv_temp2) == 0)
    # -----------------------------------------------------------------------------
    # -----------------------dry station----------------------------------
    dryer_workstation_temp_dict = defaultdict(lambda: defaultdict(list))
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, parameters, _) in enumerate(job):
            for m_id in machines:
                if "dryer_workstation" in m_id:
                    temperature = json.loads(parameters[0]["param"]["temperature"])
                    dryer_workstation_temp_dict[m_id][temperature].append(all_tasks[job_id, task_id])
    for m_id in dryer_workstation_temp_dict.keys():
        temperatures = list(dryer_workstation_temp_dict[m_id].keys())
        for i in range(len(temperatures)):
            for j in range(i + 1, len(temperatures)):
                temp1 = temperatures[i]
                temp2 = temperatures[j]
                itvs_temp1 = dryer_workstation_temp_dict[m_id][temp1]
                itvs_temp2 = dryer_workstation_temp_dict[m_id][temp2]
                for itv_temp1 in itvs_temp1:
                    for itv_temp2 in itvs_temp2:
                        mdl.add(overlap_length(itv_temp1, itv_temp2) == 0)
    # -----------------------------------------------------------------------------
    # ----------------------Add a constraint that the number of centrifuges must be even--------------------------------
    odd_punish = 0
    for m_id in machines_list:
        if "centrifugation" in m_id:
            itvs = machine_to_intervals[m_id]
            start_times = [start_of(itv) for itv in itvs]
            end_times = [end_of(itv) for itv in itvs]
            overlap_nums = []
            for t in start_times + end_times:
                overlap_num = 0
                for itv in itvs:
                    overlap_num += logical_and(start_of(itv) <= t, t < end_of(itv))
                overlap_nums.append(overlap_num)
            for num in overlap_nums:
                odd_punish += logical_and(equal(num % 2, 1), diff(num, 0))
    mdl.add(odd_punish == 0)
    # ---------------------------------------------------------------

    # --------------Constraints for new tasks: The time must be greater than cur_ptr-----------------
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, _, sche_info_dict) in enumerate(job):
            # Simulation: Used for simulation and plotting of tasks inserted midway
            if sche_info_dict["start_time"] is not None and sche_info_dict["start_time"] < cur_ptr:
                # If it has already been scheduled
                # if sche_info_dict["has_scheduled"] is not None and sche_info_dict["has_scheduled"] == True:
                pass
            # If it has not been scheduled yet
            else:
                mdl.add(start_of(all_tasks[job_id, task_id]) >= cur_ptr)
    # ---------------------------------------------------------------------

    # --------------------The starting sample racks for the same task must be taken together--------------------
    expr_no_task_0_jobs = {}
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, _, sche_info_dict) in enumerate(job):
            if task_id == 0:
                expr_no = job_id.split("_")[0]
                if expr_no not in expr_no_task_0_jobs:
                    expr_no_task_0_jobs[expr_no] = []
                expr_no_task_0_jobs[expr_no].append(all_tasks[job_id, task_id])

    for expr_no, jobs in expr_no_task_0_jobs.items():
        if len(jobs) > 1:
            base_start_time = start_of(jobs[0])
            for each_job in jobs:
                mdl.add(start_of(each_job) == base_start_time)
    # ----------------------------------------------------------------------

    # Make a machine's batch as compact as possible
    all_bias = 0
    for m_id in machines_list:
        min_start = min([start_of(itv) for itv in machine_to_intervals[m_id]])
        bias = [start_of(itv) - min_start for itv in machine_to_intervals[m_id]]
        all_bias += sum(bias)

    # Measuring
    makespan_var = max([end_of(all_tasks[job_id, len(job) - 1]) for job_id, job in jobs_data.items()])
    # mdl.minimize(makespan_var + all_bias + odd_punish)
    mdl.minimize(makespan_var + odd_punish)

    # solve
    msol = mdl.solve()

    if msol:
        print("Objective: ", msol.get_objective_value())
        cursor = conn_sql.cursor()
        cursor.execute("BEGIN")
        # Process the data into the task sequence for each machine
        for job_id, job in jobs_data.items():
            for task_id, (machines, duration, _, _) in enumerate(job):
                for m_id in machines:
                    itv = msol.get_var_solution(task_to_machine[job_id, task_id][m_id])
                    if itv.is_present():
                        cursor.execute(
                            """
                            UPDATE task_scheduled 
                            SET 
                            name = ?,
                            ws_code_fjspb = ?,
                            start_time = ?,
                            end = ?,
                            duration = ?,
                            job_length = ?
                            WHERE b_id = ? AND fjspb_index = ?""",
                            (
                                itv.get_name(),
                                itv.get_name().split("-")[2][1:],
                                itv.get_start(),
                                itv.get_end(),
                                itv.get_length(),
                                len(job),
                                itv.get_name().split("-")[0][1:],
                                int(itv.get_name().split("-")[1][1:]),
                            ),
                        )

        conn_sql.commit()

        # Traverse the entire list and update the next_step_ws_code_fjspb field for each task
        cursor.execute("BEGIN")
        cursor.execute("SELECT * FROM task_scheduled")
        column_names = [description[0] for description in cursor.description]
        rows = cursor.fetchall()

        for row in rows:
            row_data = dict(zip(column_names, row))

            cur_b_id = row_data["b_id"]
            cur_fjspb_index = row_data["fjspb_index"]

            cursor.execute(
                """
                SELECT ws_code_fjspb 
                FROM task_scheduled 
                WHERE b_id = ? AND fjspb_index = ?
                """,
                (cur_b_id, cur_fjspb_index + 1),
            )
            next_ws_code_fjspb = cursor.fetchone()
            if next_ws_code_fjspb:
                cursor.execute(
                    """
                    UPDATE task_scheduled 
                    SET next_step_ws_code_fjspb = ? 
                    WHERE b_id = ? AND fjspb_index = ?""",
                    (next_ws_code_fjspb[0], cur_b_id, cur_fjspb_index),
                )

        conn_sql.commit()

        cursor.execute("""SELECT MAX(end) FROM task_scheduled""")
        makespan = cursor.fetchone()[0]

        return makespan, machines_list, batch_capacities
    else:
        print("No solution found.")
        return None, machines_list, batch_capacities


def main():
    pass


if __name__ == "__main__":
    main()
