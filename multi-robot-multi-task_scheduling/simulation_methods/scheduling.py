import logging
import json
import time
import threading
import sys
import os
import copy
import signal
import queue
import collections
import argparse
import shutil
import select

from flask import Flask, request, make_response
from pprint import pprint
import colorama
from colorama import Fore, Style
from collections.abc import Iterable

from fespb.fespb import fespb

import sqlite3
from utils.db_tools import *

database = "/database_paper"
database_file = "/5_experiments.sqlite"

database_dir = os.path.dirname(os.path.abspath(__file__)) + database


def non_blocking_input(prompt, timeout=5):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        return sys.stdin.readline().rstrip("\n")
    else:
        return None


# Pause function, used to manually interrupt task execution
def pause_func(timeout=3):
    user_input = non_blocking_input(f"Input 1 to pause(wait {timeout} s): ", timeout=timeout)
    if user_input == "1":
        while True:
            user_input = input("Enter 1 to resume: ")
            if user_input == "1":
                print("Resume")
                break
            else:
                print("The input is not 1, please enter 1 to resume")
    else:
        pass
    return


class TaskScheduling:
    def __init__(self, flask_route="/scheduling_test", flask_port=5051, debug_mode=False):
        # --------------------LOG-----------------------------
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(logging.StreamHandler())
        # -------------------------------------------------------

        self.debug_mode = debug_mode

        # Scheduling can only begin after receiving the first frame of the task stream
        self.flag_receive_new_taskflow = False
        self.flag_reveive_first_taskflow = False
        self.flag_gen_table = False

        # Check if the current task that matches the global pointer is completed
        self.cur_matched_tasks_done = True
        # The global pointer indicates the global progress on the workstation scheduling table
        self.ws_ptr = 0
        # Global completion time calculated based on the workstation schedule
        self.makespan = 0
        # Length of the last received task, used to detect if a new task has been generated
        self.old_task_len = 0
        # Length of the new task, used to detect if a new task has been generated
        self.new_task_len = 0

        self.receive_first_dms = False

        self.msg_lock = threading.Lock()

        self.app = Flask(__name__)
        self.flask_route = flask_route
        self.flask_port = flask_port
        self.setup_routes()

        self.schedule_id = 0

        # Current scheduling commands
        self.assign_lock = threading.Lock()
        self.assign_cur_queue = queue.Queue()
        self.assign_cur_set = set()

        self.robot_list = ["robot_0", "robot_1"]
        self.robot_platform_list = ["robot_platform"]

        # Current fjspb task's machine_list
        self.machines_list = None
        self.batch_capacities = None

        # When the task that matches the global pointer is not yet completed, the pointer should not move. Complete the "take" part first, then complete the "put" part.
        self.ws_ptr_matched_tasks = {}

        # Current tasks for each robot
        self.cur_tasks_for_robots = {
            "type": None,  # Operation type
            "assign": {},  # Allocation result
            "ws_arr": collections.defaultdict(list),  # The station each robot is assigned to
        }
        # Save the current position of the bottles
        self.bottle_location = collections.defaultdict()

        self.exit_event = threading.Event()

    # Reset the environment when a batch of tasks is completed
    def reset(self):
        time_struct = time.localtime(int(time.time()))
        formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time_struct)
        target_file = os.path.join(database_dir, "task_" + formatted_time + ".sqlite")
        shutil.copy(database_dir + database_file, target_file)

        self.logger.info("Backup the database: %" + target_file)

        self.flag_receive_new_taskflow = False
        self.flag_reveive_first_taskflow = False
        self.flag_gen_table = False
        self.cur_matched_tasks_done = True
        self.ws_ptr = 0
        self.makespan = 0

        self.old_task_len = 0
        self.new_task_len = 0

        self.logger.info("Reset variables complete...")

    def setup_routes(self):
        @self.app.route(self.flask_route, methods=["POST"])
        def scheduling():
            flask_conn_sql = sqlite3.connect(database_dir + database_file)
            full_data = request.data.decode("utf-8")

            self.new_task_len = len(json.loads(full_data)["task_list"])
            with self.msg_lock:
                self.receive_first_dms = True

                # New task sequence received
                if self.new_task_len > self.old_task_len:
                    self.flag_receive_new_taskflow = True
                    self.old_task_len = self.new_task_len

                # Initialize the task database upon receiving the first task
                # Note: Receiving the first task is one way of receiving a new task
                # However, receiving a new task does not necessarily mean it is the first task
                self.flag_reveive_first_taskflow, self.ws_in_highflux = update_db(
                    self.flag_reveive_first_taskflow,
                    self.ws_ptr,
                    full_data,
                    flask_conn_sql,
                )

                if not self.flag_reveive_first_taskflow:
                    self.logger.info("waiting for task sequence...")

            time.sleep(3)

            assign_list = []
            with self.assign_lock:
                while not self.assign_cur_queue.empty():
                    try:
                        one_assign = self.assign_cur_queue.get_nowait()
                        assign_list.append(one_assign)
                    except queue.Empty:
                        self.logger.info("assign_queue empty")
                        break

            cur_msg = {
                "code": 200,
                "message": "ok",
                "data": assign_list,
            }

            response = make_response(json.dumps(cur_msg, ensure_ascii=False))
            response.headers["Content-Type"] = "application/json"

            flask_conn_sql.close()
            return response

    # thread 1: Receive task, equipment, and bottle status
    def run_flask(self):
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.CRITICAL)
        self.app.run(host="0.0.0.0", port=self.flask_port, debug=True, use_reloader=False)

    # Thread 2: Main loop for task scheduling logic
    def main_loop(self):
        main_loop_conn_sql = sqlite3.connect(database_dir + database_file)
        while not self.exit_event.is_set():
            time.sleep(1)

            with self.msg_lock:
                # Generate the scheduling table as soon as a new task stream is received
                if not self.flag_gen_table and self.flag_receive_new_taskflow:
                    # core fjspb algorithm
                    (self.makespan, self.machines_list, self.batch_capacities) = fespb(
                        self.ws_ptr, main_loop_conn_sql
                    )

                    self.bottle_location = find_bottle_location_from_db(main_loop_conn_sql)

                    if self.makespan is not None:
                        self.flag_gen_table = True
                        self.flag_receive_new_taskflow = False
                        self.cur_matched_tasks_done = True
                        # The global pointer scans from 0
                        self.ws_ptr = 0
                        self.logger.info("New scheduling table has been generated...")
                    else:
                        self.logger.error("FJSPB scheduing failed...")

            while not self.receive_first_dms:
                time.sleep(1)

            # If the scheduling table has been generated and all tasks matching the current pointer are completed, start searching for the next batch of tasks
            with self.msg_lock:
                if self.flag_gen_table and self.cur_matched_tasks_done == True:
                    self.logger.info(
                        "All tasks matching the current pointer are completed, start searching for the next batch of tasks..."
                    )

                    self.ws_ptr_matched_tasks = self.find_next_tasks(main_loop_conn_sql)
                    self.cur_matched_tasks_done = False
                    self.logger.info(
                        Fore.GREEN
                        + Style.BRIGHT
                        + f"Pointer: {self.ws_ptr}, Makespan: {self.makespan} \n"
                        + Style.RESET_ALL
                    )

            if self.makespan is not None and self.ws_ptr > self.makespan:
                self.logger.info(
                    "The global pointer has completed its traversal, all tasks are finished, waiting to update the completion status of all tasks..."
                )
                with self.msg_lock:
                    self.send_next_assignment(
                        "fake_robot" + str(time.time()),
                        "starting_station",
                        "finish",
                        main_loop_conn_sql,
                    )
                time.sleep(20)
                self.logger.info(
                    "Current task scheduling is complete, waiting for the next batch of tasks..."
                )
                with self.msg_lock:
                    self.reset()

                # pprint(self.ws_ptr_matched_tasks)

            # If the scheduling table has been generated and tasks matching the current pointer are not completed, complete the tasks one by one
            if self.flag_gen_table and self.cur_matched_tasks_done == False:
                # 1.Ensure all tasks immediately to the left of the current pointer are completed
                # 2. Workstations requiring "take" complete the "take" operation
                # 3.Workstations requiring "put" complete the "put" operation
                # 4.Workstations requiring "start," "dripping," "test," or "recycle" complete the corresponding operations

                # 1.Ensure that all tasks immediately to the left of the current pointer are completed
                self.wait_left_of_ptr_tasks_done(main_loop_conn_sql)

                # Ensure that all tasks immediately to the left of the current pointer are completed
                if self.flag_receive_new_taskflow == True:
                    self.flag_gen_table = False
                    continue

                if self.flag_gen_table:
                    # 2.Workstations that require "take" should complete the "take" operation
                    self.gen_assignment("take", main_loop_conn_sql)
                    self.send_assignment("take", main_loop_conn_sql)

                if self.flag_gen_table:
                    # 3.Workstations that require "put" should complete the "put" operation
                    self.gen_assignment("put", main_loop_conn_sql)
                    self.send_assignment("put", main_loop_conn_sql)

                if self.flag_gen_table:
                    # 4.Workstations that require "start," "dripping," "test," or "recycle" should complete the corresponding operations
                    self.handle_ws_oper(main_loop_conn_sql)

                self.cur_matched_tasks_done = True

        main_loop_conn_sql.close()

    # Workstations that require "start," "dripping," "test," or "recycle" should complete the corresponding operations
    def handle_ws_oper(self, conn_sql):
        # Check if all bottles have arrived; if they have, send a "start" instruction to the workstation
        while bool(self.ws_ptr_matched_tasks["do_start"]) and self.flag_gen_table:
            time.sleep(1)
            if self.exit_event.is_set():
                return

            with self.msg_lock:
                if self.flag_gen_table:
                    self.update_global_state(conn_sql)

            for ws_code, bottles in dict(self.ws_ptr_matched_tasks["do_start"]).items():
                start = all(self.bottle_location[b["b_id"]] == ws_code for b in bottles)
                if start:
                    time.sleep(0.1)
                    # Activate the workstation that is about to start
                    with self.msg_lock:
                        self.send_next_assignment("fake_robot" + str(time.time()), ws_code, "start", conn_sql)
                    self.ws_ptr_matched_tasks["do_start"].pop(ws_code)

        for oper in ["dripping", "test", "recycle"]:
            while bool(self.ws_ptr_matched_tasks["do_" + oper]):
                time.sleep(1)
                if self.exit_event.is_set():
                    return
                with self.msg_lock:
                    if self.flag_gen_table:
                        self.update_global_state(conn_sql)

                for ws_code, bottles in dict(self.ws_ptr_matched_tasks["do_" + oper]).items():
                    if "electrocatalysis" in ws_code:
                        start = all(
                            self.bottle_location[b["b_id"]] == "high_flux_electrocatalysis_workstation"
                            for b in bottles
                        )
                    elif "xrd" in ws_code:
                        start = all(
                            self.bottle_location[b["b_id"]] == "high_flux_xrd_workstation" for b in bottles
                        )
                    if start:
                        # Activate the workstation that is about to start
                        cmd = "electronic_" + oper if "electrocatalysis" in ws_code else "xrd_" + oper
                        with self.msg_lock:
                            self.send_next_assignment("robot_platform", ws_code, cmd, conn_sql)
                        self.ws_ptr_matched_tasks["do_" + oper].pop(ws_code)

    # Wait until all tasks at workstations immediately to the left of the current task pointer are completed
    def wait_left_of_ptr_tasks_done(self, main_loop_conn_sql):
        for ws_code in self.ws_ptr_matched_tasks["left"]:
            print(ws_code)
        print("\n")

        done = False
        while not done and self.flag_gen_table:
            done = True
            time.sleep(1)
            if self.exit_event.is_set():
                return

            if not self.debug_mode:
                pause_func()

            with self.msg_lock:
                if self.flag_gen_table:
                    self.update_global_state(main_loop_conn_sql)

            for ws_code, ws_tasks in self.ws_ptr_matched_tasks["left"].items():
                if "electrocatalysis_dripping" in ws_code:
                    done &= all(task["electronic_dripping"] for task in ws_tasks)
                elif "electrocatalysis_test" in ws_code:
                    done &= all(task["electronic_test"] for task in ws_tasks)
                elif "electrocatalysis_recycle" in ws_code:
                    done &= all(task["electronic_recycle"] for task in ws_tasks)
                elif "xrd_dripping" in ws_code:
                    done &= all(task["xrd_dripping"] for task in ws_tasks)
                elif "xrd_test" in ws_code:
                    done &= all(task["xrd_test"] for task in ws_tasks)
                elif "xrd_recycle" in ws_code:
                    done &= all(task["xrd_recycle"] for task in ws_tasks)
                else:
                    done &= all(task["start"] for task in ws_tasks)
        return

    # Send the opers from self.cur_tasks_for_robots
    def send_assignment(self, oper: str, conn_sql: sqlite3.Connection):
        self.logger.info("Send %s oper...", oper)

        with self.msg_lock:
            if self.flag_gen_table:
                self.update_global_state(conn_sql)

        # Check if there are conflicts at the destination workstation for the mobile robot
        flag_ws_conflict, ws_code_conflict_0, ws_code_conflict_1 = self.check_conflict_in_mobile_robots()

        send_robot_0 = False
        while flag_ws_conflict and self.flag_gen_table:
            if self.exit_event.is_set():
                return

            if not self.debug_mode:
                pause_func()

            with self.msg_lock:
                if self.flag_gen_table:
                    self.update_global_state(conn_sql)

            # First, let robot 0 execute tasks at the conflicting workstation ID, and send the instruction only once
            if not send_robot_0:
                send_robot_0 = True

                with self.msg_lock:
                    r_status, r_battery = find_robot_status(self.robot_list[0], conn_sql)

                one_assign_tmp = {}
                with self.msg_lock:
                    one_assign_tmp = self.send_next_assignment(
                        self.robot_list[0], ws_code_conflict_0, oper, conn_sql
                    )

                self.wait_assign_queue_empty()

                send_msg_success = None
                with self.msg_lock:
                    send_msg_success = check_bottle_records(one_assign_tmp, conn_sql)

                repeat_msg_num = 0
                while not send_msg_success:
                    if self.exit_event.is_set():
                        return

                    with self.msg_lock:
                        repeat_msg_num += 1
                        one_assign_tmp = self.send_next_assignment(
                            self.robot_list[0],
                            ws_code_conflict_0,
                            oper,
                            conn_sql,
                            resend=True,
                        )
                        print(
                            Fore.GREEN + Style.BRIGHT + f"Resend msg:{repeat_msg_num} times" + Style.RESET_ALL
                        )
                    self.wait_assign_queue_empty()
                    with self.msg_lock:
                        send_msg_success = check_bottle_records(one_assign_tmp, conn_sql)
                if send_msg_success:
                    print(Fore.GREEN + Style.BRIGHT + "operating..." + Style.RESET_ALL)

            # Check if the tasks at the conflicting workstation are completed
            if self.check_if_robot_tasks_done(oper, self.robot_list[0], ws_code_conflict_0):
                # Remove the conflicting workstation
                self.cur_tasks_for_robots["ws_arr"][self.robot_list[0]].remove(ws_code_conflict_0)

                # Continue checking if there are conflicts at the destination workstations for the two robots
                (
                    flag_ws_conflict,
                    ws_code_conflict_0,
                    ws_code_conflict_1,
                ) = self.check_conflict_in_mobile_robots()
                if flag_ws_conflict:
                    send_robot_0 = False

            time.sleep(1)

        # Check if there are conflicts between the destination workstations of the mobile robots and the platform robots
        (
            flag_ws_conflict,
            ws_id_platform,
            ws_id_robot,
        ) = self.check_conflict_in_mobile_platform_robots()

        send_robot_platform = False
        while flag_ws_conflict and self.flag_gen_table:
            if self.exit_event.is_set():
                return

            if not self.debug_mode:
                pause_func()

            with self.msg_lock:
                if self.flag_gen_table:
                    self.update_global_state(conn_sql)

            # First, let the platform robot execute tasks at the conflicting workstation ID
            if not send_robot_platform:
                send_robot_platform = True

                one_assign_tmp = {}
                with self.msg_lock:
                    one_assign_tmp = self.send_next_assignment(
                        "robot_platform", ws_id_platform, oper, conn_sql
                    )

                self.wait_assign_queue_empty()

                send_msg_success = None
                with self.msg_lock:
                    send_msg_success = check_bottle_records(one_assign_tmp, conn_sql)

                repeat_msg_num = 0
                while not send_msg_success:
                    if self.exit_event.is_set():
                        return

                    with self.msg_lock:
                        repeat_msg_num += 1
                        one_assign_tmp = self.send_next_assignment(
                            "robot_platform",
                            ws_id_platform,
                            oper,
                            conn_sql,
                            resend=True,
                        )
                        print(
                            Fore.GREEN + Style.BRIGHT + f"Resend msg:{repeat_msg_num} times" + Style.RESET_ALL
                        )
                    self.wait_assign_queue_empty()
                    with self.msg_lock:
                        send_msg_success = check_bottle_records(one_assign_tmp, conn_sql)
                if send_msg_success:
                    print(Fore.GREEN + Style.BRIGHT + "operating..." + Style.RESET_ALL)

            if self.check_if_robot_tasks_done(oper, "robot_platform", ws_id_platform) == True:
                self.cur_tasks_for_robots["ws_arr"]["robot_platform"].remove(ws_id_platform)

                (
                    flag_ws_conflict,
                    ws_id_platform,
                    ws_id_robot,
                ) = self.check_conflict_in_mobile_platform_robots()
                if flag_ws_conflict:
                    send_robot_platform = False

            time.sleep(1)

        with self.msg_lock:
            if self.flag_gen_table:
                self.update_global_state(conn_sql)

        # At the same time, a robot can only execute one task
        # If multiple workstations require the robot to execute tasks at the current time (i.e., multiple workstations are in the robot's ws_id_arr), issue tasks for each robot sequentially
        robot_ptr = {
            robot_name: len(ws_id_arr) - 1  # Here, subtracting one is for convenient indexing
            for robot_name, ws_id_arr in self.cur_tasks_for_robots["ws_arr"].items()
        }
        robot_can_proc_flag = {
            robot_name: True for robot_name, ws_id_arr in self.cur_tasks_for_robots["ws_arr"].items()
        }

        # pprint(self.bottle_location)

        all_tasks_done = True
        # First, check if all opers are completed
        for robot_name, ws_id_arr in self.cur_tasks_for_robots["ws_arr"].items():
            for ws_code in ws_id_arr:
                all_tasks_done &= self.check_if_robot_tasks_done(oper, robot_name, ws_code)

        if all_tasks_done == True:
            all_tasks_done &= self.check_if_matched_tasks_done(self.ws_ptr_matched_tasks, oper)

        while not all_tasks_done and self.flag_gen_table:
            if self.exit_event.is_set():
                return

            if not self.debug_mode:
                pause_func()

            # Send operations to each robot sequentially, with only one operation per robot at a time
            for robot_name, ws_id_arr in self.cur_tasks_for_robots["ws_arr"].items():
                if robot_ptr[robot_name] >= 0 and robot_can_proc_flag[robot_name]:
                    ws_code = ws_id_arr[robot_ptr[robot_name]]

                    self.logger.info("oper squence: ")
                    pprint(ws_id_arr)
                    self.logger.info(f"oper squence pointer: {robot_ptr[robot_name]}")

                    one_assign_tmp = {}
                    with self.msg_lock:
                        one_assign_tmp = self.send_next_assignment(robot_name, ws_code, oper, conn_sql)

                    self.wait_assign_queue_empty()

                    send_msg_success = None
                    with self.msg_lock:
                        send_msg_success = check_bottle_records(one_assign_tmp, conn_sql)

                    repeat_msg_num = 0
                    if not self.debug_mode:
                        while not send_msg_success:
                            if self.exit_event.is_set():
                                return
                            with self.msg_lock:
                                repeat_msg_num += 1
                                one_assign_tmp = self.send_next_assignment(
                                    robot_name, ws_code, oper, conn_sql, resend=True
                                )
                            self.wait_assign_queue_empty()
                            with self.msg_lock:
                                send_msg_success = check_bottle_records(one_assign_tmp, conn_sql)
                    if send_msg_success:
                        print(Fore.GREEN + Style.BRIGHT + "operating..." + Style.RESET_ALL)

                    robot_ptr[robot_name] -= 1  # Move the pointer to the next operation
                    robot_can_proc_flag[robot_name] = False

            with self.msg_lock:
                if self.flag_gen_table:
                    self.update_global_state(conn_sql)

            for robot_name, ws_id_arr in self.cur_tasks_for_robots["ws_arr"].items():
                if robot_can_proc_flag[robot_name] == False:
                    # Adding one here is to point to the previous incomplete operation and check if it is completed
                    ws_code = ws_id_arr[robot_ptr[robot_name] + 1]
                    robot_can_proc_flag[robot_name] = self.check_if_robot_tasks_done(
                        oper, robot_name, ws_code
                    )

            # Check if all operations are completed
            all_tasks_done = True
            for robot_name, ws_id_arr in self.cur_tasks_for_robots["ws_arr"].items():
                for ws_code in ws_id_arr:
                    all_tasks_done &= self.check_if_robot_tasks_done(oper, robot_name, ws_code)

            if all_tasks_done == True:
                all_tasks_done &= self.check_if_matched_tasks_done(self.ws_ptr_matched_tasks, oper)

            time.sleep(1)

            # Simulation: Used for simulation and plotting of tasks inserted midway
            if self.flag_receive_new_taskflow == True:
                self.flag_gen_table = False
                self.ws_ptr = 800
                print(Fore.YELLOW + Style.BRIGHT + "insert task..." + Style.RESET_ALL)
                return

        # After completing the operations, clear self.cur_tasks_for_robots
        self.clear_cur_robot_tasks_cache()

    def wait_assign_queue_empty(self):
        while True:
            if self.exit_event.is_set():
                return
            with self.assign_lock:
                if self.assign_cur_queue.empty():
                    break
            time.sleep(1)
        time.sleep(8)

    def check_any_task_processing(self):
        pass

    # Allocate operations to robots
    def gen_assignment(self, oper: str, conn_sql: sqlite3.Connection):
        with self.msg_lock:
            if self.flag_gen_table:
                self.update_global_state(conn_sql)

        do_oper_tasks = self.ws_ptr_matched_tasks["do_" + oper]

        if len(do_oper_tasks) == 0:
            return

        with self.msg_lock:
            self.cur_tasks_for_robots["type"] = oper
            self.cur_tasks_for_robots["assign"] = self.assign_tasks(do_oper_tasks, oper, conn_sql)

        for r_name, r_tasks in self.cur_tasks_for_robots["assign"].items():
            self.cur_tasks_for_robots["ws_arr"][r_name].extend(list(r_tasks.keys()))

    def assign_tasks(self, do_oper_tasks, oper, conn_sql: sqlite3.Connection):
        groups = {r_name: defaultdict(list) for r_name in (self.robot_list + self.robot_platform_list)}

        if oper == "put":
            # Assign "put" operations to 3 robots (2 mobile and 1 platform; the function logic can be extended to multiple robots)
            # Assign the "put" operation to the robot currently holding the bottle
            for ws_name, tasks in do_oper_tasks.items():
                for task in tasks:
                    robot_name = self.bottle_location[task["b_id"]]
                    if robot_name in groups:
                        groups[robot_name][task["ws_code_fjspb"]].append(task)
        elif oper == "take":
            # Assign bottles from the same workstation to the same robot; if the ws_id is a high-throughput workstation, the platform robot performs the operation
            # Special case for "take" operations on staging racks:
            # If odd is True, the "take" operation is directly performed by the platform robot; otherwise, it is performed by the mobile robot
            sorted_take_tasks = sorted(do_oper_tasks.items(), key=lambda x: len(x[1]), reverse=True)
            for ws_code, tasks in sorted_take_tasks:
                if ws_code in self.ws_in_highflux:
                    groups[self.robot_platform_list[0]][ws_code].extend(tasks)
                elif ws_code == "multi_robots_exchange_workstation":
                    for task in tasks:
                        if task["odd"]:
                            groups[self.robot_platform_list[0]][ws_code].append(task)
                        else:
                            groups[self.robot_list[0]][ws_code].append(task)
                else:
                    exchange_station_tasks = [
                        task
                        for task in tasks
                        if task.get("next_step_ws_code_fjspb") == "multi_robots_exchange_workstation"
                    ]
                    other_tasks = [
                        task
                        for task in tasks
                        if task.get("next_step_ws_code_fjspb") not in ["multi_robots_exchange_workstation"]
                    ]
                    if exchange_station_tasks:
                        groups[self.robot_list[0]][ws_code].extend(exchange_station_tasks)
                        if other_tasks:
                            groups[self.robot_list[0]][ws_code].extend(other_tasks)
                    else:
                        smaller_robot = min(
                            groups[self.robot_list[0]],
                            groups[self.robot_list[1]],
                            key=lambda x: sum(len(tasks) for tasks in x.values()),
                        )
                        smaller_robot[ws_code].extend(tasks)
                    # --------------------------------------------
        return groups

    def send_next_assignment(
        self, robot_name, ws_code, oper: str, conn_sql: sqlite3.Connection, resend=False
    ):
        if not resend:
            self.schedule_id += 1

        assign_ws_code = (
            "high_flux_electrocatalysis_workstation"
            if "electrocatalysis" in ws_code
            else "high_flux_xrd_workstation" if "xrd" in ws_code else ws_code
        )

        one_assignment = {
            "scheduleId": "{:06d}".format(self.schedule_id),
            "stamp": int(time.time() * 1000),
            "operation": oper,
            "workstation": assign_ws_code,
            "robot": robot_name,
            "bottleList": [],
            "parameters": [],
            "time": None,
        }

        if oper == "finish":
            expr_no_to_steps = find_expr_no_to_steps_from_db(conn_sql)
            one_assignment["bottleList"] = [
                {
                    "expr_no": expr_no,
                    "stepId": step_info["step_id"],
                    "branch_code": step_info["branch_code"],
                    "index": step_index,
                }
                for expr_no, steps in expr_no_to_steps.items()
                for step_index, step_info in steps.items()
            ]
        elif oper in ["take", "put"]:
            for b_task in self.cur_tasks_for_robots["assign"][robot_name][ws_code]:
                task_info = fetch_task_info_from_db(b_task["b_id"], int(b_task["fjspb_index"]), conn_sql)
                b_id_actual = find_b_no_map_from_db(b_task["b_id"], actual_to_vials=False, conn_sql=conn_sql)

                b_msg = {
                    "expr_no": task_info["expr_no"],
                    "branch_code": 0,
                    "expr_name": task_info["expr_name"],
                    "index": task_info["fjspb_index"],
                    "stepId": task_info["step_id"],
                    "bottleCode": (b_id_actual if b_id_actual else b_task["b_id"].split("_")[1]),
                    "material": None,
                    "material_code": None,
                    "value": None,
                }

                one_assignment["parameters"] = task_info["parameters"]
                one_assignment["bottleList"].append(b_msg)

            if one_assignment["workstation"] == "starting_station":
                one_assignment["parameters"][0]["param"]["bottle_count"] = str(
                    len(one_assignment["bottleList"])
                )
        else:  # oper == "start"
            key_mapping = {
                "start": "do_start",
                "dripping": "do_dripping",
                "test": "do_test",
                "recycle": "do_recycle",
            }
            key = next((key_mapping[k] for k in key_mapping if k in oper), None)

            for b_task in self.ws_ptr_matched_tasks[key][ws_code]:
                task_info = fetch_task_info_from_db(b_task["b_id"], int(b_task["fjspb_index"]), conn_sql)
                b_id_actual = find_b_no_map_from_db(b_task["b_id"], actual_to_vials=False, conn_sql=conn_sql)

                b_msg = {
                    "expr_no": task_info["expr_no"],
                    "branch_code": 0,
                    "expr_name": task_info["expr_name"],
                    "index": task_info["fjspb_index"],
                    "stepId": task_info["step_id"],
                    "bottleCode": (b_id_actual if b_id_actual else b_task["b_id"].split("_")[1]),
                    "material": None,
                    "concentration": None,
                    "concentration_unit_code": None,
                    "material_code": None,
                    "value": None,
                }

                one_assignment["parameters"] = task_info["parameters"]
                one_assignment["time"] = task_info["step_raw_time"]

                # liquid or soild station
                if isinstance(task_info["detail"]["material"], Iterable):
                    for idx, values in enumerate(task_info["detail"]["material"]):
                        material_full_info = task_info["detail"]["material"][idx]
                        if material_full_info.split("_")[0] != "None":
                            b_msg["material"] = material_full_info.split("_")[0]
                        if material_full_info.split("_")[1] != "None":
                            b_msg["concentration"] = float(material_full_info.split("_")[1])
                        if material_full_info.split("_")[2] != "None":
                            b_msg["concentration_unit_code"] = material_full_info.split("_")[2]
                        b_msg["material_code"] = task_info["detail"]["material_code"][idx]
                        b_msg["value"] = task_info["detail"]["value"][idx]
                        one_assignment["bottleList"].append(copy.deepcopy(b_msg))
                else:
                    one_assignment["bottleList"].append(b_msg)

        with self.assign_lock:
            self.assign_cur_queue.put(one_assignment)
        if not resend:
            pprint(one_assignment)

        return one_assignment

    def clear_cur_robot_tasks_cache(self):
        self.cur_tasks_for_robots = {
            "type": None,
            "assign": {},
            "ws_arr": collections.defaultdict(list),
        }

    def check_if_robot_tasks_done(self, oper, robot_name, ws_code) -> bool:
        return all(r_task[oper] for r_task in self.cur_tasks_for_robots["assign"][robot_name][ws_code])

    # Check for conflicts between destination workstations of mobile robots and return the ID of the first conflicting destination workstation
    def check_conflict_in_mobile_robots(self):
        # Physically conflicting workstations
        conflict_ws_pairs = [
            [
                "imbibition_workstation",
                "dryer_workstation_1",
                "new_centrifugation_screen",
            ],
            [
                "liquid_dispensing_1",
                "magnetic_stirring_2",
                "magnetic_stirring_1",
                "magnetic_stirring",
            ],
            [
                "solid_dispensing",
                "solid_dispensing_1",
                "magnetic_stirring_2",
                "magnetic_stirring_1",
                "magnetic_stirring",
            ],
            [
                "magnetic_stirring",
                "solid_dispensing_1",
                "solid_dispensing",
                "liquid_dispensing",
            ],
            ["gc", "capping_station"],
        ]
        ws_list_0 = self.cur_tasks_for_robots["ws_arr"][self.robot_list[0]]
        ws_list_1 = self.cur_tasks_for_robots["ws_arr"][self.robot_list[1]]
        for ws_id_0 in ws_list_0:
            for ws_id_1 in ws_list_1:
                if ws_id_0 == ws_id_1:
                    return True, ws_id_0, ws_id_1
                for pair in conflict_ws_pairs:
                    if ws_id_0 in pair and ws_id_1 in pair:
                        return True, ws_id_0, ws_id_1
        return False, None, None

    # Check for conflicts between the destination workstations of mobile robots and platform robots, and return the ID of the first conflicting destination workstation
    def check_conflict_in_mobile_platform_robots(self):
        # Physically conflicting workstations
        conflict_ws_pairs = [
            [
                "multi_robots_exchange_workstation",
                "high_flux_electrocatalysis_workstation",
            ],
            ["multi_robots_exchange_workstation", "fluorescence"],
            ["multi_robots_exchange_workstation", "high_flux_xrd_workstation"],
            ["multi_robots_exchange_workstation", "libs"],
            ["multi_robots_exchange_workstation", "uv_vis"],
        ]
        robot_ws = []
        for robot in self.robot_list:
            robot_ws.extend(self.cur_tasks_for_robots["ws_arr"][robot])
        platform_ws = self.cur_tasks_for_robots["ws_arr"]["robot_platform"]

        for ws_id_platform in platform_ws:
            for ws_id_robot in robot_ws:
                if ws_id_platform == ws_id_robot:
                    return True, ws_id_platform, ws_id_robot
                for pair in conflict_ws_pairs:
                    if ws_id_platform in pair and ws_id_robot in pair:
                        return True, ws_id_platform, ws_id_robot

        return False, None, None

    # Check if all "do_put" or "do_take" parts in matched_tasks are completed. Note that if matched_tasks is empty, return true
    def check_if_matched_tasks_done(self, tasks: dict, oper: str) -> bool:
        for ws_tasks in tasks.get("do_" + oper, {}).values():
            for task in ws_tasks:
                b_id = task["b_id"]
                if oper == "take":
                    if self.bottle_location[b_id] not in (self.robot_list + self.robot_platform_list):
                        return False
                elif oper == "put":
                    if self.bottle_location[b_id] in (self.robot_list + self.robot_platform_list):
                        return False
                if not task[oper]:
                    return False
        return True

    # Move the global pointer to find the next sequence of operations to be performed
    def find_next_tasks(self, conn_sql: sqlite3.Connection):
        while self.ws_ptr <= self.makespan:
            # When searching for the next sequence of operations, first increment the pointer by 1
            self.ws_ptr += 1
            ws_ptr_matched_tasks = find_matching_tasks_from_db(self.ws_ptr, conn_sql)
            if any(ws_ptr_matched_tasks.get(key) for key in ws_ptr_matched_tasks if key != "left"):
                break
        return ws_ptr_matched_tasks

    # Update the global operation status and bottle positions
    def update_global_state(self, conn_sql: sqlite3.Connection):
        self.bottle_location = find_bottle_location_from_db(conn_sql)

        # 1. update self.ws_ptr_matched_tasks
        conn_sql.execute("BEGIN")
        for key in [
            "do_take",
            "do_put",
            "do_start",
            "do_dripping",
            "do_test",
            "do_recycle",
            "left",
        ]:
            self.ws_ptr_matched_tasks[key] = {
                ws_code: [
                    fetch_task_info_from_db(
                        ptr_task["b_id"],
                        ptr_task["fjspb_index"],
                        conn_sql,
                        full_info=True,
                    )
                    for ptr_task in ws_tasks
                ]
                for ws_code, ws_tasks in self.ws_ptr_matched_tasks[key].items()
            }
        conn_sql.commit()

        # 2. pdate self.cur_tasks_for_robots from the database to show whether the current operations for robots are completed
        conn_sql.execute("BEGIN")
        for r_name, r_tasks in self.cur_tasks_for_robots["assign"].items():
            for ws_id, ws_tasks in r_tasks.items():
                self.cur_tasks_for_robots["assign"][r_name][ws_id] = [
                    fetch_task_info_from_db(task["b_id"], task["fjspb_index"], conn_sql, full_info=True)
                    for task in ws_tasks
                ]
        conn_sql.commit()

        return

    def signal_handler(self, sig, frame):
        self.logger.info("\nExiting gracefully...")
        self.exit_event.set()

    def run(self):
        self.thread_connect_dms = threading.Thread(target=self.run_flask, daemon=True)
        self.thread_connect_dms.start()

        self.thread_main_loop = threading.Thread(target=self.main_loop)
        self.thread_main_loop.start()

        signal.signal(signal.SIGINT, self.signal_handler)
        while not self.exit_event.is_set():
            time.sleep(0.5)


if __name__ == "__main__":
    colorama.init()
    parser = argparse.ArgumentParser(description="FJSPB Scheduling")
    parser.add_argument("--debug", action="store_true", default=False, help="enable debug mode")
    args = parser.parse_args()

    try:
        if args.debug:
            print(Fore.RED + Style.BRIGHT + "Debug mode..." + Style.RESET_ALL)
            flask_route, flask_port = "/scheduling_test", 5051
        else:
            flask_route, flask_port = "/scheduling", 5050

        debug_mode = args.debug

        TS = TaskScheduling(flask_route=flask_route, flask_port=flask_port, debug_mode=debug_mode)
        TS.run()
    except Exception as e:
        print(e)
