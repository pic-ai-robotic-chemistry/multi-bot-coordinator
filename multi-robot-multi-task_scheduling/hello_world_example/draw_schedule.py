import sqlite3
import os
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches

from collections import defaultdict
from utils.db_tools import *

colors = list(mcolors.CSS4_COLORS.keys())


database = "/data"
database_file = "/simple_example.sqlite"
database_dir = os.path.dirname(os.path.abspath(__file__)) + database


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

    cursor.execute("""SELECT MAX(end) FROM task_scheduled""")
    makespan = cursor.fetchone()[0]

    cursor.execute("SELECT vials_no, actual_no FROM bottle_info")
    vials_to_actual_dict = defaultdict(list)
    for row in cursor.fetchall():
        vials_no, actual_no = row
        vials_to_actual_dict[vials_no] = actual_no

    cursor.execute("SELECT * FROM task_scheduled ORDER BY start_time")
    tasks_info = cursor.fetchall()

    bottle_table = defaultdict(list)
    for row in tasks_info:
        task_data = dict(
            zip([description[0] for description in cursor.description], row)
        )
        b_id = task_data["b_id"]
        bottle_table[b_id].append(task_data)

    conn_sql.close()

    ws_code_to_color = {}
    fig, ax = plt.subplots()

    for idx, (job_id, tasks) in enumerate(bottle_table.items()):
        for task in tasks:
            ws_code_fjspb = task["ws_code_fjspb"]
            ws_code_to_color[ws_code_fjspb] = mcolors.CSS4_COLORS[
                colors[hash(task["ws_code_fjspb"]) % len(colors)]
            ]
            ax.broken_barh(
                [(task["start_time"], task["duration"])],
                (idx - 0.4, 0.8),
                facecolors=ws_code_to_color[ws_code_fjspb],
            )

    ax.axvline(x=makespan, color="r", linestyle="-", label="Makespan")

    ax.set_yticks(range(len(bottle_table)))
    ax.set_yticklabels(["bottle"])

    for idx, (job_id, tasks) in enumerate(bottle_table.items()):
        ax.axhline(y=idx - 0.5, color="grey", linestyle="--", linewidth=0.5)

    ax.set_ylim(ymin=-0.5, ymax=len(bottle_table) - 0.5)
    ax.set_xlim(xmin=0)

    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    current_ticks = list(ax.get_xticks())
    current_labels = list(ax.get_xticklabels())
    current_ticks.append(makespan)
    current_labels.append(f"{makespan}")

    ax.set_xticks(current_ticks)
    ax.set_xticklabels(current_labels)

    ax.set_xlabel("Time", fontsize=16)
    ax.set_ylabel("Experiments", fontsize=16)
    ax.set_title("Bottle Perspective", fontsize=16)

    legend_patches = []
    seen_labels = set()
    for ws_code_fjspb, color in ws_code_to_color.items():
        label = ws_code_fjspb
        color = ws_code_to_color[ws_code_fjspb]
        if label not in seen_labels:
            seen_labels.add(label)
            legend_patches.append(mpatches.Patch(color=color, label=label))

    legend = ax.legend(
        handles=legend_patches, loc="upper left", fontsize=10, bbox_to_anchor=(0.0, 1.0)
    )
    legend.get_frame().set_edgecolor("none")

    plt.show()
