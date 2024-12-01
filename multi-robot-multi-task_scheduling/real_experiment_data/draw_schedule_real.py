import collections
import random
import sqlite3
import argparse
import os
import pandas as pd
import matplotlib
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
database_file = "/task_e1_real.sqlite"
database_dir = os.path.dirname(os.path.abspath(__file__)) + database

SPECIFIC_COLORS = {
    "e1": "firebrick",
    "e2": "darkorange",
    "e3": "green",
    "e4": "royalblue",
}

if __name__ == "__main__":
    conn_sql = sqlite3.connect(database_dir + database_file)
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

    task_height = 0.3
    expr_name_to_color = {}

    # Initialize the minimum start time and maximum end time.
    min_start_time = None
    max_finish_time = None

    # Draw only the machines that have tasks.
    actual_machines_list = []
    for m_id in machines_list:
        if not ws_table[m_id]:
            continue
        actual_machines_list.append(m_id)

    for m_index, m_id in enumerate(actual_machines_list):
        for task in ws_table[m_id]:
            if task["ws_code_fjspb"] == "starting_station" and task["fjspb_index"] == 0:
                if task["take_create_time"] is not None:
                    start_time = pd.to_datetime(task["take_create_time"])
                    if min_start_time is None or start_time < min_start_time:
                        min_start_time = start_time

                if task["take_finish_time"] is not None:
                    finish_time = pd.to_datetime(task["take_finish_time"])
                    if max_finish_time is None or finish_time > max_finish_time:
                        max_finish_time = finish_time

            elif (
                task["ws_code_fjspb"] == "starting_station"
                and task["fjspb_index"] == task["job_length"] - 1
            ):
                if task["start_create_time"] is not None:
                    start_time = pd.to_datetime(task["start_create_time"])
                    if min_start_time is None or start_time < min_start_time:
                        min_start_time = start_time

                if task["start_finish_time"] is not None:
                    finish_time = pd.to_datetime(task["start_finish_time"])
                    if max_finish_time is None or finish_time > max_finish_time:
                        max_finish_time = finish_time

            else:
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
                    if task[oper + "_create_time"] is not None:
                        start_time = pd.to_datetime(task[oper + "_create_time"])
                        if min_start_time is None or start_time < min_start_time:
                            min_start_time = start_time

                    if task[oper + "_finish_time"] is not None:
                        finish_time = pd.to_datetime(task[oper + "_finish_time"])
                        if max_finish_time is None or finish_time > max_finish_time:
                            max_finish_time = finish_time

    # Draw a bottle scheduling table.
    fig1, ax1 = plt.subplots()

    all_times = []

    for idx, (job_id, tasks) in enumerate(bottle_table.items()):
        for task in tasks:
            job_id = task["name"].split("-")[0][1:]
            expr_name = task["expr_name"][0:2]
            if expr_name not in expr_name_to_color:
                if expr_name in SPECIFIC_COLORS:
                    expr_name_to_color[expr_name] = SPECIFIC_COLORS[expr_name]
                else:
                    expr_name_to_color[expr_name] = mcolors.CSS4_COLORS[
                        colors[hash(expr_name) % len(colors)]
                    ]
            color = expr_name_to_color[expr_name]

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
                    ax1.broken_barh(
                        [(mdates.date2num(start_time), duration / (24 * 60 * 60))],
                        (idx - 0.5, 1),
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
                    # The unit is seconds.
                    duration = (finish_time - start_time).total_seconds()

                    # Here, draw the actual time, in days.
                    ax1.broken_barh(
                        [(mdates.date2num(start_time), duration / (24 * 60 * 60))],
                        (idx - 0.5, 1),
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
                            # -1 is to avoid errors.
                            if duration < int(task["record_time"]) * 60 - 1:
                                finish_time = start_time + pd.to_timedelta(
                                    int(task["record_time"]) * 60, unit="s"
                                )

                        all_times.append((start_time, finish_time))
                        exist_task = True

                if exist_task:
                    # The unit is seconds.
                    duration = (finish_time - start_time).total_seconds()

                    # Here, draw the actual time, in days.
                    if task["record_time"] != None and int(task["record_time"]) > 0:
                        # -1 is to avoid errors.
                        if duration < int(task["record_time"]) * 60 - 1:
                            duration += int(task["record_time"]) * 60

                    ax1.broken_barh(
                        [(mdates.date2num(start_time), duration / (24 * 60 * 60))],
                        (idx - 0.5, 1),
                        facecolors=color,
                        edgecolor="none",
                    )

    for idx, (job_id, tasks) in enumerate(bottle_table.items()):
        ax1.axhline(y=idx - 0.5, color="grey", linestyle="--", linewidth=0.5)

    ax1.set_yticks(range(len(bottle_table)))
    ax1.set_yticklabels(
        [("bottle {}".format(b_id[-6:])) for b_id in bottle_table.keys()],
        fontsize=10,
    )

    ax1.set_ylim(ymin=-0.5, ymax=len(bottle_table) - 0.5)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M:%S"))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=1))

    fig1.autofmt_xdate()

    xticks = list(ax1.get_xticks())
    if min_start_time is not None:
        ax1.axvline(x=min_start_time, color="red", linestyle="--", linewidth=1)
        xticks.append(mdates.date2num(min_start_time))
    if max_finish_time is not None:
        ax1.axvline(x=max_finish_time, color="blue", linestyle="--", linewidth=1)
        xticks.append(mdates.date2num(max_finish_time))
    ax1.set_xticks(xticks)
    # ax1.tick_params(axis='x', labelsize=8)

    ax1.set_xlabel("Time", fontsize=16)
    ax1.set_ylabel("Experiments", fontsize=16)
    ax1.set_title("Experiment Perspective", fontsize=16)
    plt.tight_layout()

    time_difference = max_finish_time - min_start_time
    days = time_difference.days
    hours, remainder = divmod(time_difference.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    print(f"Start time: {min_start_time}")
    print(f"End time: {max_finish_time}")
    print(f"Makespan: {days} days {hours} hours {minutes} minutes {seconds} seconds")

    # Merge all time intervals to calculate idle time.
    merged_times = []
    for start, end in sorted(all_times):
        if merged_times and start <= merged_times[-1][1]:
            merged_times[-1] = (merged_times[-1][0], max(merged_times[-1][1], end))
        else:
            merged_times.append((start, end))

    # Calculate idle time.
    idle_time = pd.Timedelta(0)
    for i in range(1, len(merged_times)):
        idle_time += merged_times[i][0] - merged_times[i - 1][1]

    idle_days = idle_time.days
    idle_hours, remainder = divmod(idle_time.seconds, 3600)
    idle_minutes, idle_seconds = divmod(remainder, 60)

    print(
        f"Non-experiment operations: {idle_days} days {idle_hours} hours {idle_minutes} minutes {idle_seconds} seconds"
    )
    # pprint(merged_times)

    # Calculate the difference between the total time and the transit time.
    active_time = time_difference - idle_time
    active_days = active_time.days
    active_hours, remainder = divmod(active_time.seconds, 3600)
    active_minutes, active_seconds = divmod(remainder, 60)
    print(
        f"Time spent on experiments: {active_days} days {active_hours} hours {active_minutes} minutes {active_seconds} seconds"
    )

    # Calculate the operation ratio of the robot.
    put_robot_count = {"robot_0": 0, "robot_1": 0, "robot_platform": 0}
    take_robot_count = {"robot_0": 0, "robot_1": 0, "robot_platform": 0}

    # Traverse all tasks and count the number of robot operations.
    for idx, (job_id, tasks) in enumerate(bottle_table.items()):
        for task in tasks:
            # Count the number of operations for put_robot.
            if task["put_robot"] is not None:
                if task["put_robot"] in put_robot_count:
                    put_robot_count[task["put_robot"]] += 1
                else:
                    put_robot_count[task["put_robot"]] = 1

            # Count the number of operations for take_robot.
            if task["take_robot"] is not None:
                if task["take_robot"] in take_robot_count:
                    take_robot_count[task["take_robot"]] += 1
                else:
                    take_robot_count[task["take_robot"]] = 1

    total_put_operations = sum(put_robot_count.values())
    total_take_operations = sum(take_robot_count.values())

    put_robot_0_ratio = (
        put_robot_count["robot_0"] / total_put_operations
        if total_put_operations > 0
        else 0
    )
    put_robot_1_ratio = (
        put_robot_count["robot_1"] / total_put_operations
        if total_put_operations > 0
        else 0
    )
    put_robot_platform_ratio = (
        put_robot_count["robot_platform"] / total_put_operations
        if total_put_operations > 0
        else 0
    )

    take_robot_0_ratio = (
        take_robot_count["robot_0"] / total_take_operations
        if total_take_operations > 0
        else 0
    )
    take_robot_1_ratio = (
        take_robot_count["robot_1"] / total_take_operations
        if total_take_operations > 0
        else 0
    )
    take_robot_platform_ratio = (
        take_robot_count["robot_platform"] / total_take_operations
        if total_take_operations > 0
        else 0
    )

    print(f"Total number of put operations: {total_put_operations}")
    print(
        f"Number of operations for robot_0: {put_robot_count['robot_0']}/{total_put_operations}({put_robot_0_ratio:.2%})"
    )
    print(
        f"Number of operations for robot_1: {put_robot_count['robot_1']}/{total_put_operations}({put_robot_1_ratio:.2%})"
    )
    print(
        f"Number of operations for robot_platform: {put_robot_count['robot_platform']}/{total_put_operations}({put_robot_platform_ratio:.2%})"
    )
    print(f"Total number of take operations: {total_take_operations}")
    print(
        f"Number of operations for robot_0: {take_robot_count['robot_0']}/{total_take_operations}({take_robot_0_ratio:.2%})"
    )
    print(
        f"Number of operations for robot_1: {take_robot_count['robot_1']}/{total_take_operations}({take_robot_1_ratio:.2%})"
    )
    print(
        f"Number of operations for robot_platform: {take_robot_count['robot_platform']}/{total_take_operations}({take_robot_platform_ratio:.2%})"
    )

    print("Participation ratio:")
    print(
        f"Number of operations for robot_0: {2 * take_robot_count['robot_0']}/{2 * total_take_operations}({take_robot_0_ratio:.2%})"
    )
    print(
        f"Number of operations for robot_1: {2 * take_robot_count['robot_1']}/{2 * total_take_operations}({take_robot_1_ratio:.2%})"
    )
    print(
        f"Number of operations for robot_platform: {2 * take_robot_count['robot_platform']}/{2 * total_take_operations}({take_robot_platform_ratio:.2%})"
    )

    plt.show()
