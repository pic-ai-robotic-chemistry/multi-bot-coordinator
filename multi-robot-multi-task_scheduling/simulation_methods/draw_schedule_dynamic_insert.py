import sqlite3
import sqlite3
import os
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from collections import defaultdict
from utils.db_tools import *

colors = list(mcolors.CSS4_COLORS.keys())

unit_oper_time = 2
num_robot = 2

database = "/database_paper"
database_file_1 = "/e1.sqlite"
database_file_2 = "/e2.sqlite"
database_file_3 = "/e3.sqlite"
database_file_4 = "/e4.sqlite"
database_file_5 = "/e5.sqlite"
database_file_0 = "/4_experiments.sqlite"
database_file_6 = "/5_experiments.sqlite"

database_dir = os.path.dirname(os.path.abspath(__file__)) + database

matplotlib.rcParams["font.family"] = "AR PL UMing CN"

SPECIFIC_COLORS = {
    "e1": "firebrick",
    "e2": "darkorange",
    "e3": "green",
    "e4": "royalblue",
    "e5": "purple",
}

expr_name_to_color = {}


def plot_bottle_db(fig, ax, offset, makespan_offset, database_file_name):
    conn_sql = sqlite3.connect(database_dir + database_file_name)
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

    cursor = conn_sql.cursor()
    cursor.execute("""SELECT MAX(end) FROM task_scheduled""")

    makespan = cursor.fetchone()[0]

    cursor.execute("SELECT vials_no, actual_no FROM bottle_info")
    vials_to_actual_dict = defaultdict(list)
    for row in cursor.fetchall():
        vials_no, actual_no = row
        vials_to_actual_dict[vials_no] = actual_no

    cursor.execute("SELECT * FROM task_scheduled ORDER BY start_time")
    tasks_info = cursor.fetchall()

    ws_table = defaultdict(list)
    for row in tasks_info:
        task_data = dict(zip([description[0] for description in cursor.description], row))
        ws_code = task_data["ws_code_fjspb"]
        ws_table[ws_code].append(task_data)

    bottle_table = defaultdict(list)
    for row in tasks_info:
        task_data = dict(zip([description[0] for description in cursor.description], row))
        b_id = task_data["b_id"]
        bottle_table[b_id].append(task_data)

    conn_sql.close()

    # For plotting: If it’s experiment 1, sort the bottles
    if "STC202407060956465669_1" in bottle_table.keys():
        order = ["STC202407060956465669_3", "STC202407060956465669_1", "STC202407060956465669_2"]
        sorted_bottle_table = {k: bottle_table[k] for k in order}
        bottle_table = sorted_bottle_table

    # For plotting: If it’s a parallel experiment, sort the bottles
    if "STC202407061009554526_1" in bottle_table.keys():
        order = [
            "e1-bottles-3",
            "e2-bottles-10",
            "e2-bottles-4",
            "e3-bottles-4",
            "e4-bottles-10",
            "e4-bottles-5",
            "e5-bottles-2",
        ]
        experiment_counts = {}
        for key, value in bottle_table.items():
            expr_base = value[0]["expr_name"].split("-")[0][0:2]
            if expr_base in experiment_counts:
                experiment_counts[expr_base] += 1
            else:
                experiment_counts[expr_base] = 1
        culmu_height = 0
        sorted_experiment_counts = dict(sorted(experiment_counts.items()))
        for expr, count in sorted_experiment_counts.items():
            culmu_height += count
            ax.axhline(y=culmu_height - 0.5, color="black", linestyle="--", linewidth=0.8)

        order_index = {name: idx for idx, name in enumerate(order)}
        sorted_bottle_table = dict(
            sorted(bottle_table.items(), key=lambda item: order_index[item[1][0]["expr_name"]])
        )
        b_id_order = ["STC202407061009554526_3", "STC202407061009554526_2", "STC202407061009554526_1"]
        b_id_order_index = {b_id: idx for idx, b_id in enumerate(b_id_order)}
        final_sorted_bottle_table = {
            k: v
            for k, v in sorted(
                sorted_bottle_table.items(),
                key=lambda item: b_id_order_index.get(item[0], len(b_id_order_index)),
            )
        }
        bottle_table = final_sorted_bottle_table

    # Calculate the maximum number of tasks processed simultaneously on each machine
    machine_max_tasks = {}
    for m_id in machines_list:
        # Skip if the machine has no tasks
        if not ws_table[m_id]:
            continue
        # Calculate the last time of the task in this machine
        max_time = max(task["end"] for task in ws_table[m_id])
        time_task_count = {}
        for t in range(max_time + 1):
            time_task_count[t] = 0
            for task in ws_table[m_id]:
                # Count only the number of tasks whose start time equals the current pointer time
                if task["start_time"] == t:
                    time_task_count[t] += 1
        machine_max_tasks[m_id] = max(time_task_count.values())

    actual_machines_list = [m_id for m_id in machines_list if m_id in machine_max_tasks]

    task_height = 0.3

    # Calculate the height occupied on the y-axis for each machine and the starting position on the y-axis for each machine
    machine_y_height = {m_id: task_height * machine_max_tasks[m_id] for m_id in actual_machines_list}

    machine_y_start = {}
    cumulative_height = 0
    for m_id in actual_machines_list:
        machine_y_start[m_id] = cumulative_height
        cumulative_height += machine_y_height[m_id]

    def calculate_gap_time(pointer, ws_table, unit_oper_time, num_robot):
        num_oper = 0
        num_ws = 0
        ws_task_count = {}

        max_ptr_end_time = 0

        # Calculate the number of tasks to the left and right of the pointer
        for m_id in machines_list:
            for task in ws_table[m_id]:
                if task["end"] == pointer:
                    num_ws += 1
                    if m_id in ws_task_count:
                        ws_task_count[m_id] += 1
                    else:
                        ws_task_count[m_id] = 1
                if task["start_time"] == pointer:
                    num_oper += 1

                # Calculate the maximum task end time at the current pointer
                if task["end"] > pointer and task["start_time"] < pointer:
                    max_ptr_end_time = max(task["end"], max_ptr_end_time)

        # For cases where task["end"] == pointer
        if num_ws > 0:
            task_counts = sorted(ws_task_count.values(), reverse=True)
            robot_task_counts = [0] * num_robot

            for i, count in enumerate(task_counts):
                robot_task_counts[i % num_robot] += count

            min_gap_time = max(robot_task_counts) * unit_oper_time
        else:
            min_gap_time = unit_oper_time

        # For cases where task["start_time"] == pointer
        return max(min_gap_time, round(num_oper * unit_oper_time / num_robot)), max_ptr_end_time

    gap_itvs = []

    pointer = 0
    max_ptr_end_time = 0
    while True:
        any_task_adjusted = False
        for m_id in machines_list:
            for task in ws_table[m_id]:
                # gao calculate for experiment 1
                if "1" in database_file_name:
                    if task["end"] == pointer and pointer < 10 or task["end"] == pointer and pointer > 1800:
                        dynamic_gap_time, max_ptr_end_time = calculate_gap_time(
                            pointer, ws_table, unit_oper_time, num_robot
                        )

                        if [pointer, pointer + dynamic_gap_time] not in gap_itvs:
                            gap_itvs.append([pointer, pointer + dynamic_gap_time])
                        # print(task)
                        for m_id_inner in machines_list:
                            for task_inner in ws_table[m_id_inner]:
                                if task_inner["start_time"] >= pointer:
                                    task_inner["start_time"] += dynamic_gap_time
                                    task_inner["end"] += dynamic_gap_time

                        any_task_adjusted = True
                        # If multiple tasks end at the same pointer position, move forward only once
                        break
                    elif task["end"] == pointer:
                        dynamic_gap_time, max_ptr_end_time = calculate_gap_time(
                            pointer, ws_table, unit_oper_time, num_robot
                        )

                        if [pointer, pointer + dynamic_gap_time] not in gap_itvs:
                            gap_itvs.append([pointer, pointer + dynamic_gap_time])
                        # print(task)
                        for m_id_inner in machines_list:
                            for task_inner in ws_table[m_id_inner]:
                                if (
                                    task_inner["start_time"] >= pointer
                                    and task_inner["start_time"] < max_ptr_end_time
                                ):
                                    task_inner["start_time"] += dynamic_gap_time
                                    task_inner["end"] += dynamic_gap_time

                        any_task_adjusted = True
                        # If multiple tasks end at the same pointer position, move forward only once
                        break
                else:
                    if task["end"] == pointer:
                        dynamic_gap_time, max_ptr_end_time = calculate_gap_time(
                            pointer, ws_table, unit_oper_time, num_robot
                        )

                        if [pointer, pointer + dynamic_gap_time] not in gap_itvs:
                            gap_itvs.append([pointer, pointer + dynamic_gap_time])
                        # print(task)
                        for m_id_inner in machines_list:
                            for task_inner in ws_table[m_id_inner]:
                                if task_inner["start_time"] >= pointer:
                                    task_inner["start_time"] += dynamic_gap_time
                                    task_inner["end"] += dynamic_gap_time

                        any_task_adjusted = True
                        # If multiple tasks end at the same pointer position, move forward only once
                        break
            # If multiple tasks end at the same pointer position, move forward only once
            if any_task_adjusted:
                break

        pointer += 1
        max_end_time = max(task["end"] for tasks in ws_table.values() for task in tasks)
        if not any_task_adjusted and pointer >= max_end_time:
            break

    # draw gaps
    def is_in_gap(pointer, gap_intervals):
        for gap_start, gap_end in gap_intervals:
            if gap_start <= pointer < gap_end:
                return True
        return False

    # Update bottle_table using ws_table
    for ws_code, tasks in ws_table.items():
        for task in tasks:
            b_id = task["b_id"]
            fjspb_index = task["fjspb_index"]
            for b_task in bottle_table[b_id]:
                if b_task["ws_code_fjspb"] == ws_code and b_task["fjspb_index"] == fjspb_index:
                    b_task["start_time"] = task["start_time"]
                    b_task["end"] = task["end"]
                    break

    for idx, (job_id, tasks) in enumerate(bottle_table.items()):
        for task in tasks:
            expr_name = task["expr_name"][0:2]
            if expr_name not in expr_name_to_color:
                if expr_name in SPECIFIC_COLORS:
                    expr_name_to_color[expr_name] = SPECIFIC_COLORS[expr_name]
                else:
                    expr_name_to_color[expr_name] = mcolors.CSS4_COLORS[colors[hash(expr_name) % len(colors)]]
            color = expr_name_to_color[expr_name]
            ax.broken_barh(
                [(task["start_time"] + makespan_offset, task["duration"])],
                (idx + offset - 0.5, 1),
                facecolors=color,
            )

    pointer = 0
    max_end_time = max(task["end"] for tasks in ws_table.values() for task in tasks)
    while pointer < max_end_time:
        if is_in_gap(pointer, gap_itvs):
            # draw grey vertial line representing the transfer time
            # ax.broken_barh(
            #     [(pointer + makespan_offset, 1)],
            #     (offset - 0.5, len(bottle_table)),
            #     facecolors="black",
            #     edgecolor="none",
            #     alpha=0.1,
            # )
            pass
        pointer += 1

    # for idx, (job_id, tasks) in enumerate(bottle_table.items()):
    #     ax.axhline(y=idx + offset - 0.5, color="grey", linestyle="--", linewidth=0.5)

    return bottle_table, ws_table, max_end_time


if __name__ == "__main__":
    cumul_offset = 0
    makespan_offset = 0
    cumul_labels = []

    # draw gantt
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8, 6), sharex=False, gridspec_kw={"height_ratios": [1, 1], "hspace": 0.1}
    )

    start_time = 0
    # parallel experiment
    cumul_offset = 0
    makespan_offset = 0
    cumul_labels = []

    bottle_table, ws_table, makespan = plot_bottle_db(fig, ax1, 0, 0, database_file_0)
    cumul_offset += len(bottle_table)
    makespan_offset += makespan
    specific_time_0 = makespan_offset
    ylabels = [
        ("{}-{}".format(bottle_table[b_id][0]["expr_name"][0:2], b_id.split("_")[1]))
        for b_id in bottle_table.keys()
    ]
    cumul_labels.extend(ylabels)

    bottle_table, ws_table, makespan = plot_bottle_db(
        fig, ax1, cumul_offset, makespan_offset, database_file_5
    )
    cumul_offset += len(bottle_table)
    makespan_offset += makespan
    specific_time_5 = makespan_offset
    ylabels = [
        ("{}-{}".format(bottle_table[b_id][0]["expr_name"][0:2], b_id.split("_")[1]))
        for b_id in bottle_table.keys()
    ]
    cumul_labels.extend(ylabels)

    # ax1.set_yticklabels(
    #     cumul_labels,
    #     fontsize=10,
    # )
    ax1.set_yticklabels([])
    ax1.set_yticks(range(cumul_offset))
    ax1.set_ylim(ymin=-0.5, ymax=cumul_offset - 0.5)

    ax1.axvline(specific_time_0, color="r", linestyle="--")

    ax1.set_xlim([start_time, specific_time_5])
    ax1.set_xticks([start_time, specific_time_0, specific_time_5])
    ax1.set_xticklabels([start_time, specific_time_0, specific_time_5], fontsize=16)

    bottle_table, ws_table, makespan = plot_bottle_db(fig, ax2, 0, 0, database_file_6)
    specific_time_6 = makespan

    # ax2.set_yticklabels(
    #     cumul_labels,
    #     fontsize=10,
    # )
    ax2.set_yticklabels([])
    ax2.set_yticks(range(len(bottle_table)))
    ax2.set_ylim(ymin=-0.5, ymax=len(bottle_table) - 0.5)

    ax2.axvline(specific_time_6, color="r", linestyle="--")
    ax2.axvline(800, color="r", linestyle="--")

    ax2.set_xlim([start_time, specific_time_5])
    ax2.set_xticks([start_time, 800, specific_time_6])
    ax2.set_xticklabels([start_time, 800, specific_time_6], fontsize=16)

    ax2.set_xlabel("Time(min)", fontsize=16)

    plt.tight_layout()
    plt.show()
