import sqlite3
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches

from pprint import pprint
from collections import defaultdict

from utils.db_tools import *

colors = list(mcolors.CSS4_COLORS.keys())
whites = [
    "white",
    "whitesmoke",
    "snow",
    "seashell",
    "linen",
    "ivory",
    "honeydew",
    "floralwhite",
    "ghostwhite",
    "aliceblue",
    "azure",
    "mintcream",
    "oldlace",
    "antiquewhite",
]
colors = [color for color in colors if color not in whites]

import sqlite3
import os

database = "/database_paper"
database_file = "/4_experiments.sqlite"

database_dir = os.path.dirname(os.path.abspath(__file__)) + database

matplotlib.rcParams["font.family"] = "Arial"

SPECIFIC_COLORS = {
    "Gap": "black",
    "实验1": "firebrick",
    "实验2": "darkorange",
    "实验3": "green",
    "实验4": "royalblue",
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

    # Draw Gantt charts
    fig1, ax1 = plt.subplots()

    # Calculate the maximum number of tasks processed simultaneously on each machine
    machine_max_tasks = {}
    for m_id in machines_list:
        if not ws_table[m_id]:  # Skip if the machine has no tasks
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

    # task height in the Fantt chart
    task_height = 0.3

    # Calculate the height occupied on the y-axis for each machine and the starting position on the y-axis for each machine
    machine_y_height = {m_id: task_height * machine_max_tasks[m_id] for m_id in actual_machines_list}

    machine_y_start = {}
    cumulative_height = 0
    for m_id in actual_machines_list:
        machine_y_start[m_id] = cumulative_height
        cumulative_height += machine_y_height[m_id]

    expr_name_to_color = {}

    for m_index, m_id in enumerate(actual_machines_list):
        current_y_base = machine_y_start[m_id]
        last_end = -1
        current_y = current_y_base
        for task in ws_table[m_id]:
            job_id = task["name"].split("-")[0][1:]

            bar_height = task_height

            if last_end <= task["start_time"]:
                current_y = current_y_base
            else:
                current_y += bar_height
            last_end = task["end"]

            expr_name = task["expr_name"][4:7]

            if expr_name not in expr_name_to_color:
                if expr_name in SPECIFIC_COLORS:
                    expr_name_to_color[expr_name] = SPECIFIC_COLORS[expr_name]
                else:
                    expr_name_to_color[expr_name] = mcolors.CSS4_COLORS[colors[hash(expr_name) % len(colors)]]
            color = expr_name_to_color[expr_name]

            ax1.broken_barh(
                [(task["start_time"], task["duration"])],
                (current_y, bar_height),
                facecolors=color,
                edgecolor="none",
            )

            text_x = task["start_time"] + task["duration"] / 2
            text_y = current_y + (bar_height / 2)

            b_id = vials_to_actual_dict[job_id] if vials_to_actual_dict[job_id] is not None else job_id

            e_name = task["expr_name"][4:]
            step = int(task["name"].split("-")[1][1:]) + 1
            # ax1.text(text_x, text_y, f"{e_name}S{step}{m_id}", ha="center", va="center", fontsize=16)

    ax1.axvline(x=makespan, color="r", linestyle="-", label="Makespan")
    ax1.axvline(x=cur_ptr, color="r", linestyle="--", label="cur_ptr")

    yticks = [machine_y_start[m_id] + machine_y_height[m_id] / 2 for m_id in actual_machines_list]
    yticklabels = [f"M{idx}" for idx, m in enumerate(actual_machines_list)]

    # Separate each machine
    for m_id in actual_machines_list:
        ax1.axhline(y=machine_y_start[m_id], color="grey", linestyle="--", linewidth=0.5)

    ax1.set_yticks(yticks)
    ax1.set_yticklabels(yticklabels, fontsize=10)

    ax1.set_ylim(0, cumulative_height)
    ax1.set_xlim(left=0, right=1923)

    ax1.set_xticks([0, makespan])
    ax1.set_xticklabels([0, makespan], fontsize=16)

    ax1.set_xlabel("Time", fontsize=16)
    ax1.set_ylabel("Machines", fontsize=16)
    ax1.set_title("Workstation Perspective", fontsize=16)

    legend_patches = [
        mpatches.Patch(color=color, label=expr_name) for expr_name, color in expr_name_to_color.items()
    ]
    # ax1.legend(handles=legend_patches, loc="upper left", fontsize=10, bbox_to_anchor=(1.01, 1.01))

    plt.tight_layout()

    fig3, ax3 = plt.subplots()

    order = [
        "仿真多机实验1-3个瓶子-1",
        "仿真多机实验2-10个瓶子-1",
        "仿真多机实验2-4个瓶子-1",
        "仿真多机实验3-4个瓶子-1",
        "仿真多机实验4-10个瓶子-1",
        "仿真多机实验4-5个瓶子-1",
    ]

    experiment_counts = {}
    for key, value in bottle_table.items():
        expr_base = value[0]["expr_name"].split("-")[0][4:7]
        if expr_base in experiment_counts:
            experiment_counts[expr_base] += 1
        else:
            experiment_counts[expr_base] = 1
    culmu_height = 0
    sorted_experiment_counts = dict(sorted(experiment_counts.items()))
    for expr, count in sorted_experiment_counts.items():
        culmu_height += count
        ax3.axhline(y=culmu_height - 0.5, color="black", linestyle="--", linewidth=0.8)
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
            expr_name = task["expr_name"][4:7]
            # expr_name = job_id
            if expr_name not in expr_name_to_color:
                if expr_name in SPECIFIC_COLORS:
                    expr_name_to_color[expr_name] = SPECIFIC_COLORS[expr_name]
                else:
                    expr_name_to_color[expr_name] = mcolors.CSS4_COLORS[colors[hash(expr_name) % len(colors)]]
            color = expr_name_to_color[expr_name]

            ax3.broken_barh(
                [(task["start_time"], task["duration"])],
                (idx - 0.5, 1),
                facecolors=color,
            )

    ax3.axvline(x=makespan, color="r", linestyle="-", label="Makespan")

    ax3.set_yticks(range(len(bottle_table)))
    ax3.set_yticklabels([])

    # Separate each task
    # for idx, (job_id, tasks) in enumerate(bottle_table.items()):
    #     ax3.axhline(y=idx - 0.5, color="grey", linestyle="--", linewidth=0.5)

    ax3.set_ylim(ymin=-0.5, ymax=len(bottle_table) - 0.5)
    ax3.set_xlim(left=0, right=2000)

    current_ticks = [0]
    current_labels = [0]
    current_ticks.append(makespan)
    current_labels.append(f"{makespan}")

    ax3.set_xticks(current_ticks)
    ax3.set_xticklabels(current_labels)

    # ax3.set_xlabel("Time", fontsize=16)
    # ax3.set_ylabel("Experimental tasks", fontsize=16)
    # ax3.set_title("Experimental task Perspective", fontsize=16)
    plt.tight_layout()

    plt.show()
