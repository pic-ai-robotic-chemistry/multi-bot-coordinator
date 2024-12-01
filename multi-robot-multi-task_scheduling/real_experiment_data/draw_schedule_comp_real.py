import collections
import random
import sqlite3
import argparse
import sqlite3
import os
import pandas as pd
import matplotlib
from datetime import datetime
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from pprint import pprint
from collections import defaultdict
from utils.db_tools import *
from utils.render_tools import *

colors = list(mcolors.CSS4_COLORS.keys())

database = "/data"
database_file_1 = "/task_e1_real.sqlite"
database_file_2 = "/task_e2_real.sqlite"
database_file_3 = "/task_e3_real.sqlite"
database_file_4 = "/task_e4_real.sqlite"
database_file_0 = "/task_mix_real.sqlite"
database_dir = os.path.dirname(os.path.abspath(__file__)) + database

SPECIFIC_COLORS = {
    "e1": "firebrick",
    "e2": "darkorange",
    "e3": "green",
    "e4": "royalblue",
    "transfer_station": "#A77D9A",
    "dispensing": "#EFDBB9",
    "muffle_furnace": "#F4DFDD",
    "magnetic": "#A3CDEA",
    "xrd": "#9C98E9",
    "capping_station": "#D2D2D2",
    "photocatalysis_workstation_1": "#FF6145",
    "gc": "#5F9C76",
    "new_centrifugation_screen": "#BDC314",
    "imbibition_workstation": "#AFC778",
    "electrocatalysis": "#F09496",
    "dryer_workstation_1": "#F5AB5E",
    "fluorescence": "#947959",
}

expr_name_to_color = {}
ws_code_to_color = {}


def plot_db(fig, ax, offset, database_file_name, ws_color=False):
    conn_sql = sqlite3.connect(database_dir + database_file_name)
    jobs_data = construct_real_data_from_db(conn_sql)

    machines_list = []
    for job_id, job in jobs_data.items():
        for task_id, (machines, duration, _, _) in enumerate(job):
            for m_id in machines:
                if m_id not in machines_list:
                    machines_list.append(m_id)

    cursor = conn_sql.cursor()

    cursor.execute("SELECT vials_no, actual_no FROM bottle_info")
    vials_to_actual_dict = defaultdict(list)
    for row in cursor.fetchall():
        vials_no, actual_no = row
        vials_to_actual_dict[vials_no] = actual_no

    cursor.execute("SELECT * FROM task_scheduled")
    ws_table = defaultdict(list)
    tasks_info = cursor.fetchall()
    for row in tasks_info:
        task_data = dict(
            zip([description[0] for description in cursor.description], row)
        )
        ws_code = task_data["ws_code_fjspb"]
        ws_table[ws_code].append(task_data)

    bottle_table = defaultdict(list)
    for row in tasks_info:
        task_data = dict(
            zip([description[0] for description in cursor.description], row)
        )
        b_id = task_data["b_id"]
        bottle_table[b_id].append(task_data)

    conn_sql.close()

    # Sort to ensure the drawing is orderly.
    if "STC202407011507324187_1" in bottle_table.keys():
        order = [
            "STC202407011507461832_1",
            "STC202407011507324187_1",
            "STC202407011507383458_1",
        ]
        sorted_bottle_table = {k: bottle_table[k] for k in order}
        bottle_table = sorted_bottle_table

    # Sort to ensure the drawing is orderly.
    if "STC202407061018443648_1" in bottle_table.keys():
        order = [
            "e1-bottle-600-1-mix",
            "e1-bottle-500-1-mix",
            "e1-bottle-550-1-mix",
            "e2-bottles-10-mix",
            "e2-bottles-4-mix",
            "e3-bottles-4-mix",
            "e4-bottles-10-mix",
            "e4-bottles-5-mix",
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
            ax.axhline(
                y=culmu_height - 0.5, color="black", linestyle="--", linewidth=0.8
            )

        order_index = {name: idx for idx, name in enumerate(order)}
        sorted_bottle_table = dict(
            sorted(
                bottle_table.items(),
                key=lambda item: order_index[item[1][0]["expr_name"]],
            )
        )
        bottle_table = sorted_bottle_table

    all_times = []
    for idx, (_, tasks) in enumerate(bottle_table.items()):
        for task in tasks:
            if not ws_color:
                expr_name = task["expr_name"][0:2]
                if expr_name not in expr_name_to_color:
                    if expr_name in SPECIFIC_COLORS:
                        expr_name_to_color[expr_name] = SPECIFIC_COLORS[expr_name]
                    else:
                        expr_name_to_color[expr_name] = mcolors.CSS4_COLORS[
                            colors[hash(expr_name) % len(colors)]
                        ]
                color = expr_name_to_color[expr_name]
            else:
                ws_code_fjspb = task["ws_code_fjspb"]
                if (
                    "starting_station" in ws_code_fjspb
                    or "multi_robots_exchange_workstation" in ws_code_fjspb
                ):
                    ws_code_to_color[ws_code_fjspb] = SPECIFIC_COLORS[
                        "transfer_station"
                    ]
                elif "dispensing" in ws_code_fjspb:
                    ws_code_to_color[ws_code_fjspb] = SPECIFIC_COLORS["dispensing"]
                elif "xrd" in ws_code_fjspb:
                    ws_code_to_color[ws_code_fjspb] = SPECIFIC_COLORS["xrd"]
                elif "electrocatalysis" in ws_code_fjspb:
                    ws_code_to_color[ws_code_fjspb] = SPECIFIC_COLORS[
                        "electrocatalysis"
                    ]
                elif "magnetic" in ws_code_fjspb:
                    ws_code_to_color[ws_code_fjspb] = SPECIFIC_COLORS["magnetic"]
                else:
                    ws_code_to_color[ws_code_fjspb] = SPECIFIC_COLORS[ws_code_fjspb]

                color = ws_code_to_color[ws_code_fjspb]

            # Boundary conditions
            if task["ws_code_fjspb"] == "starting_station" and task["fjspb_index"] == 0:
                if (
                    task["take_create_time"] is not None
                    and task["take_finish_time"] is not None
                ):
                    start_time = pd.to_datetime(task["take_create_time"])
                    finish_time = pd.to_datetime(task["take_finish_time"])
                    all_times.append((start_time, finish_time))

                    # The unit is seconds.
                    duration = (finish_time - start_time).total_seconds()

                    # Here, draw the actual time, in days.
                    ax.broken_barh(
                        [(mdates.date2num(start_time), duration / (24 * 60 * 60))],
                        (idx + offset - 0.5, 1),
                        facecolors=color,
                        edgecolor="none",
                    )
            # Boundary conditions
            elif (
                task["ws_code_fjspb"] == "starting_station"
                and task["fjspb_index"] == task["job_length"] - 1
            ):
                if (
                    task["start_create_time"] is not None
                    and task["start_finish_time"] is not None
                ):
                    start_time = pd.to_datetime(task["start_create_time"])
                    finish_time = pd.to_datetime(task["start_finish_time"])
                    all_times.append((start_time, finish_time))

                    duration = (finish_time - start_time).total_seconds()

                    ax.broken_barh(
                        [(mdates.date2num(start_time), duration / (24 * 60 * 60))],
                        (idx + offset - 0.5, 1),
                        facecolors=color,
                        edgecolor="none",
                    )
            else:
                exist_task = False
                oper_list = [
                    "start",
                    "xrd_dripping",
                    "xrd_test",
                    "xrd_recycle",
                    "electronic_dripping",
                    "electronic_test",
                    "electronic_recycle",
                ]
                for oper in oper_list:
                    if (
                        task[oper + "_create_time"] is not None
                        and task[oper + "_finish_time"] is not None
                    ):
                        start_time = pd.to_datetime(task[oper + "_create_time"])
                        finish_time = pd.to_datetime(task[oper + "_finish_time"])

                        if (
                            task["record_time"] is not None
                            and int(task["record_time"]) > 0
                        ):
                            duration = (finish_time - start_time).total_seconds()
                            # -1是为了避免误差
                            if duration < int(task["record_time"]) * 60 - 1:
                                finish_time = start_time + pd.to_timedelta(
                                    int(task["record_time"]) * 60, unit="s"
                                )

                        all_times.append((start_time, finish_time))
                        exist_task = True

                if exist_task:

                    duration = (finish_time - start_time).total_seconds()

                    if task["record_time"] != None and int(task["record_time"]) > 0:
                        # -1 is to avoid errors.
                        if duration < int(task["record_time"]) * 60 - 1:
                            duration += int(task["record_time"]) * 60

                    ax.broken_barh(
                        [(mdates.date2num(start_time), duration / (24 * 60 * 60))],
                        (idx + offset - 0.5, 1),
                        facecolors=color,
                        edgecolor="none",
                    )

    return bottle_table


if __name__ == "__main__":
    cumul_offset = 0
    cumul_labels = []

    fig, (ax, ax1, ax2) = plt.subplots(
        3,
        1,
        figsize=(16, 12),
        sharex=True,
        gridspec_kw={"height_ratios": [1, 1, 1], "hspace": 0.1},
    )

    # e1
    bottle_table = plot_db(fig, ax, cumul_offset, database_file_1)
    cumul_offset += len(bottle_table)
    ax.axhline(y=cumul_offset - 0.5, color="black", linestyle="--", linewidth=0.8)

    # e2
    bottle_table = plot_db(fig, ax, cumul_offset, database_file_2)
    cumul_offset += len(bottle_table)
    ax.axhline(y=cumul_offset - 0.5, color="black", linestyle="--", linewidth=0.8)

    # e3
    bottle_table = plot_db(fig, ax, cumul_offset, database_file_3)
    cumul_offset += len(bottle_table)
    ax.axhline(y=cumul_offset - 0.5, color="black", linestyle="--", linewidth=0.8)

    # e4
    bottle_table = plot_db(fig, ax, cumul_offset, database_file_4)
    cumul_offset += len(bottle_table)
    ax.axhline(y=cumul_offset - 0.5, color="black", linestyle="--", linewidth=0.8)

    ax.set_yticklabels([])
    ax.set_yticks(range(cumul_offset))
    ax.set_ylim(ymin=-0.5, ymax=cumul_offset - 0.5)

    start_time = datetime(2024, 7, 1, 15, 7, 53)

    # e1 | e2 | e3
    specific_time_1 = datetime(2024, 7, 2, 23, 36, 3)
    specific_time_2 = datetime(2024, 7, 3, 21, 32, 26)
    specific_time_3 = datetime(2024, 7, 4, 11, 25, 15)

    # e4
    end_time = datetime(2024, 7, 4, 15, 38, 45)

    # mix
    specific_time_4 = datetime(2024, 7, 3, 10, 8, 7)

    ax.axvline(specific_time_1, color="r", linestyle="--")
    ax.axvline(specific_time_2, color="r", linestyle="--")
    ax.axvline(specific_time_3, color="r", linestyle="--")

    ax.set_xlim([start_time, end_time])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M:%S"))
    ax.set_xticks(
        [
            start_time,
            specific_time_1,
            specific_time_4,
            specific_time_2,
            specific_time_3,
            end_time,
        ]
    )
    ax.set_xticklabels([])

    # mix
    bottle_table = plot_db(fig, ax1, 0, database_file_0)
    ax1.set_yticklabels([])
    ax1.set_yticks(range(len(bottle_table)))
    ax1.set_ylim(ymin=-0.5, ymax=len(bottle_table) - 0.5)
    ax1.axvline(specific_time_4, color="r", linestyle="--")

    bottle_table = plot_db(fig, ax2, 0, database_file_0, ws_color=True)
    ax2.set_yticklabels([])
    ax2.set_yticks(range(len(bottle_table)))
    ax2.set_ylim(ymin=-0.5, ymax=len(bottle_table) - 0.5)
    ax2.set_xticklabels([])

    ax2.axvline(specific_time_4, color="r", linestyle="--")

    legend_patches = []
    seen_labels = set()
    for ws_code_fjspb, color in ws_code_to_color.items():
        if (
            "starting_station" in ws_code_fjspb
            or "multi_robots_exchange_workstation" in ws_code_fjspb
        ):
            label = "Sample rack station, Multi-robot exchange station"
        elif "dispensing" in ws_code_fjspb:
            label = (
                "Liquid station 1, Liquid station 2, Solid station 1, Solid station 2"
            )
        elif "xrd" in ws_code_fjspb:
            label = "PXRD station"
        elif "electrocatalysis" in ws_code_fjspb:
            label = "Electrocatalytic station"
        elif "magnetic" in ws_code_fjspb:
            label = "Magnetic stirring station 1, Magnetic stirring station 2"
        elif "muffle_furnace" in ws_code_fjspb:
            label = "Calcination station"
        elif "new_centrifugation_screen" in ws_code_fjspb:
            label = "Centrifuge station"
        elif "photocatalysis_workstation_1" in ws_code_fjspb:
            label = "Photocatalytic station"
        elif "dryer_workstation_1" in ws_code_fjspb:
            label = "Drying station"
        elif "capping_station" in ws_code_fjspb:
            label = "Encapsulation station"
        elif "gc" in ws_code_fjspb:
            label = "Gas chromatography station"
        elif "imbibition_workstation" in ws_code_fjspb:
            label = "Aspiration station"
        elif "fluorescence" in ws_code_fjspb:
            label = "Fluorescence spectroscopy station"
        else:
            label = ws_code_fjspb

        color = ws_code_to_color[ws_code_fjspb]
        if label not in seen_labels:
            seen_labels.add(label)
            legend_patches.append(mpatches.Patch(color=color, label=label))

    # legend = ax2.legend(
    #     handles=legend_patches, loc="upper left", fontsize=10, bbox_to_anchor=(0.6, 0.8)
    # )
    # legend.get_frame().set_edgecolor("none")

    plt.tight_layout()
    plt.show()
