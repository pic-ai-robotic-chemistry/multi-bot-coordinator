import sqlite3
import os
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from collections import defaultdict
from utils.db_tools import *

colors = list(mcolors.CSS4_COLORS.keys())

database = "/database_paper"
database_file = "/4_experiments.sqlite"

database_dir = os.path.dirname(os.path.abspath(__file__)) + database

matplotlib.rcParams["font.family"] = "Arial"

SPECIFIC_COLORS = {
    "Gap": "black",
    "e1": "firebrick",
    "e2": "darkorange",
    "e3": "green",
    "e4": "royalblue",
}

if __name__ == "__main__":
    conn_sql = sqlite3.connect(database_dir + database_file)
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

    cursor.execute("""SELECT name, value FROM global_ptr_info""")
    cur_ptr = cursor.fetchone()[1]

    # Sort the task sequence on each machine by their start time
    cursor.execute("""SELECT MAX(end) FROM task_scheduled""")
    makespan = cursor.fetchone()[0]

    cursor.execute("SELECT vials_no, actual_no FROM bottle_info")
    vials_to_actual_dict = defaultdict(list)
    for row in cursor.fetchall():
        vials_no, actual_no = row
        vials_to_actual_dict[vials_no] = actual_no

    cursor.execute("SELECT * FROM task_scheduled ORDER BY start_time")
    ws_table = defaultdict(list)
    tasks_info = cursor.fetchall()
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

    machine_max_tasks = {}
    actual_machines_list = []
    for m_id in machines_list:
        if not ws_table[m_id]:  # Skip if the machine has no tasks
            continue
        actual_machines_list.append(m_id)

    # task height in the Fantt chart
    task_height = 0.3

    expr_name_to_color = {}

    fig, ax = plt.subplots()

    order = [
        "e1-bottles-3",
        "e2-bottles-10",
        "e2-bottles-4",
        "e3-bottles-4",
        "e4-bottles-10",
        "e4-bottles-5",
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

    for idx, (job_id, tasks) in enumerate(bottle_table.items()):
        for task in tasks:
            expr_name = task["expr_name"][0:2]
            # expr_name = job_id
            if expr_name not in expr_name_to_color:
                if expr_name in SPECIFIC_COLORS:
                    expr_name_to_color[expr_name] = SPECIFIC_COLORS[expr_name]
                else:
                    expr_name_to_color[expr_name] = mcolors.CSS4_COLORS[colors[hash(expr_name) % len(colors)]]
            color = expr_name_to_color[expr_name]

            ax.broken_barh(
                [(task["start_time"], task["duration"])],
                (idx - 0.5, 1),
                facecolors=color,
            )

    ax.axvline(x=makespan, color="r", linestyle="-", label="Makespan")

    ax.set_yticks(range(len(bottle_table)))
    ax.set_yticklabels([])

    # Separate each task
    # for idx, (job_id, tasks) in enumerate(bottle_table.items()):
    #     ax.axhline(y=idx - 0.5, color="grey", linestyle="--", linewidth=0.5)

    ax.set_ylim(ymin=-0.5, ymax=len(bottle_table) - 0.5)
    ax.set_xlim(left=0, right=2000)

    current_ticks = [0]
    current_labels = [0]
    current_ticks.append(makespan)
    current_labels.append(f"{makespan}")

    ax.set_xticks(current_ticks)
    ax.set_xticklabels(current_labels)

    # ax.set_xlabel("Time", fontsize=16)
    # ax.set_ylabel("Experimental tasks", fontsize=16)
    # ax.set_title("Experimental task Perspective", fontsize=16)
    plt.tight_layout()

    plt.show()
