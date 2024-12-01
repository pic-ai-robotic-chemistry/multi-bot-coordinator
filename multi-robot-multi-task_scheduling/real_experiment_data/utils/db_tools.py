import sqlite3
import json
import time
import colorama
from colorama import Fore, Style
from collections import defaultdict
from pprint import pprint

colorama.init()


# Clear and initialize the database tables
def reset_db(conn_sql):
    cursor = conn_sql.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    for table in tables:
        if table[0] != "sqlite_sequence":
            cursor.execute(f"DROP TABLE {table[0]}")
    conn_sql.commit()

    # station info
    cursor.execute(
        """CREATE TABLE ws_info (
                    code TEXT PRIMARY KEY,
                    workstationType TEXT,
                    name TEXT,
                    capacity INTEGER,
                    section TEXT,
                    channel TEXT,
                    channel_code TEXT,
                    exist TEXT,
                    remark TEXT
                )"""
    )
    # robot info
    cursor.execute(
        """CREATE TABLE robot_info (
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    status TEXT,
                    electricityQuantity INTEGER
                )"""
    )
    # global pointer
    cursor.execute(
        """CREATE TABLE global_ptr_info (
                    name TEXT PRIMARY KEY,
                    value INTEGER 
                )"""
    )
    # task info
    cursor.execute(
        """CREATE TABLE task_scheduled (
                    name TEXT,
                    
                    b_id TEXT,
                    fjspb_index INTEGER,
                    
                    expr_name TEXT,
                    expr_no TEXT,
                    step_id INTEGER,
                    step_index INTEGER,
                    branch_code INTEGER,
                    ws_code TEXT,
                    ws_arr TEXT,
                    ws_code_fjspb TEXT,
                    next_step_ws_code_fjspb TEXT,
                    time INTEGER,
                    step_raw_time INTEGER,
                    record_time INTEGER,
                    
                    detail TEXT,
                    parameters TEXT,
                    start_time INTEGER,
                    end INTEGER,
                    duration INTEGER,
                    job_length INTEGER,
                    
                    has_scheduled BOOLEAN,
                    
                    odd BOOLEAN,
                    put BOOLEAN,
                    take BOOLEAN,
                    start BOOLEAN,
                    
                    put_robot TEXT,
                    take_robot TEXT,
                    
                    electronic_dripping BOOLEAN,
                    electronic_test BOOLEAN,
                    electronic_recycle BOOLEAN,
                    
                    xrd_dripping BOOLEAN,
                    xrd_test BOOLEAN,
                    xrd_recycle BOOLEAN,
                    
                    put_create_time TEXT,
                    put_finish_time TEXT,
                    take_create_time TEXT,
                    take_finish_time TEXT,
                    start_create_time TEXT,
                    start_finish_time TEXT,
                    
                    electronic_dripping_finish_time TEXT,
                    electronic_test_finish_time TEXT,
                    electronic_recycle_finish_time TEXT,
                    
                    xrd_dripping_finish_time TEXT,
                    xrd_test_finish_time TEXT,
                    xrd_recycle_finish_time TEXT,
                    
                    electronic_dripping_create_time TEXT,
                    electronic_test_create_time TEXT,
                    electronic_recycle_create_time TEXT,
                    
                    xrd_dripping_create_time TEXT,
                    xrd_test_create_time TEXT,
                    xrd_recycle_create_time TEXT,
                    
                    PRIMARY KEY (b_id, fjspb_index)
                )"""
    )
    # bottle info
    cursor.execute(
        """CREATE TABLE bottle_info (
                    vials_no TEXT PRIMARY KEY,
                    actual_no TEXT,
                    expr_no TEXT,
                    expr_name TEXT,
                    location TEXT,
                    FOREIGN KEY (vials_no) REFERENCES task_scheduled (b_id)
                )"""
    )
    # oper record
    cursor.execute(
        """CREATE TABLE bottle_record (
                    vials_no TEXT ,
                    createdTime TEXT,
                    updatedTime TEXT,
                    expr_no TEXT,
                    ws_code TEXT,
                    oper TEXT,
                    robot TEXT,
                    status TEXT,
                    step_index INTEGER,
                    finish_time INTEGER,
                    time INTEGER,
                    PRIMARY KEY (vials_no, createdTime)
                )"""
    )
    # oper record real time
    cursor.execute(
        """CREATE TABLE bottle_record_real (
                    vials_no TEXT ,
                    createdTime TEXT,
                    updatedTime TEXT,
                    expr_no TEXT,
                    ws_code TEXT,
                    oper TEXT,
                    robot TEXT,
                    status TEXT,
                    step_index INTEGER,
                    finish_time INTEGER,
                    time INTEGER,
                    PRIMARY KEY (vials_no, createdTime)
                )"""
    )
    conn_sql.commit()

    return


# update database
def update_db(flag_init_task, cur_ws_ptr, full_data, conn_sql):
    msg = json.loads(full_data)

    task_list, bottle_record_list, robot_list, ws_list = (
        msg["task_list"],
        msg["bottle_execute_record_list"],
        msg["robot_list"],
        msg["workstation_list"],
    )

    cursor = conn_sql.cursor()

    # If operations are not initialized, perform a database clean-up and reset
    if not flag_init_task:
        reset_db(conn_sql)

    try:
        # -----------------------update pointer---------------------
        conn_sql.execute("BEGIN")
        cursor.execute(
            "INSERT OR REPLACE INTO global_ptr_info (name, value) VALUES (?, ?)",
            ("cur_ws_ptr", cur_ws_ptr),
        )
        conn_sql.commit()
        # -----------------------------------------------------------

        # -----------------------update robot info---------------------
        conn_sql.execute("BEGIN")
        for ws in ws_list:
            if "robot" in ws["code"] and "robots" not in ws["code"]:
                cursor.execute(
                    "INSERT OR REPLACE INTO robot_info (code, name, status, electricityQuantity) VALUES (?, ?, ?, ?)",
                    (ws["code"], ws["name"], ws["status"], ws["electricityQuantity"]),
                )
        conn_sql.commit()
        # -----------------------------------------------------------

        # ----------------------update station info -----------------------
        conn_sql.execute("BEGIN")
        for ws in ws_list:
            section_flatten = "_".join(
                section["sectionCode"] for section in ws["sectionList"]
            )
            bottleSlotCount = ws["bottleSlotCount"]

            channel_list = []
            channel_code_list = []
            # Channel information for the dispensing station
            if "dispensing" in ws["code"]:
                for machine in ws["machineList"]:
                    if (
                        "channelList" in machine.keys()
                        and machine["channelList"] is not None
                    ):
                        for channel in machine["channelList"]:
                            channel_info = f'{channel["formula"]}_{channel["concentration"]}_{channel["concentrationUnitCode"]}'

                            channel_list.append(channel_info)
                            channel_code_list.append(channel["materialCode"])

            if ws["code"] in ["multi_robots_exchange_workstation"]:
                bottleSlotCount = 10
            if ws["code"] in ["starting_station"]:
                bottleSlotCount = 40
            if ws["code"] in ["high_flux_electrocatalysis_workstation"]:
                bottleSlotCount = 5
                cursor.execute(
                    "INSERT OR IGNORE INTO ws_info (code, workstationType, name, capacity, section, channel, channel_code, exist, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "high_flux_electrocatalysis_dripping",
                        "high_flux_electrocatalysis_dripping",
                        ws["name"],
                        bottleSlotCount,
                        section_flatten,
                        ",".join(channel_list),
                        ",".join(channel_code_list),
                        "dummy",
                        ws["remark"],
                    ),
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO ws_info (code, workstationType, name, capacity, section, channel, channel_code, exist, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "high_flux_electrocatalysis_test",
                        "high_flux_electrocatalysis_test",
                        ws["name"],
                        bottleSlotCount,
                        section_flatten,
                        ",".join(channel_list),
                        ",".join(channel_code_list),
                        "dummy",
                        ws["remark"],
                    ),
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO ws_info (code, workstationType, name, capacity, section, channel, channel_code, exist, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "high_flux_electrocatalysis_recycle",
                        "high_flux_electrocatalysis_recycle",
                        ws["name"],
                        bottleSlotCount,
                        section_flatten,
                        ",".join(channel_list),
                        ",".join(channel_code_list),
                        "dummy",
                        ws["remark"],
                    ),
                )
            if ws["code"] in ["high_flux_xrd_workstation"]:
                bottleSlotCount = 1
                cursor.execute(
                    "INSERT OR IGNORE INTO ws_info (code, workstationType, name, capacity, section, channel, channel_code, exist, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "high_flux_xrd_dripping",
                        "high_flux_xrd_dripping",
                        ws["name"],
                        bottleSlotCount,
                        section_flatten,
                        ",".join(channel_list),
                        ",".join(channel_code_list),
                        "dummy",
                        ws["remark"],
                    ),
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO ws_info (code, workstationType, name, capacity, section, channel, channel_code, exist, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "high_flux_xrd_test",
                        "high_flux_xrd_test",
                        ws["name"],
                        bottleSlotCount,
                        section_flatten,
                        ",".join(channel_list),
                        ",".join(channel_code_list),
                        "dummy",
                        ws["remark"],
                    ),
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO ws_info (code, workstationType, name, capacity, section, channel, channel_code, exist, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "high_flux_xrd_recycle",
                        "high_flux_xrd_recycle",
                        ws["name"],
                        bottleSlotCount,
                        section_flatten,
                        ",".join(channel_list),
                        ",".join(channel_code_list),
                        "dummy",
                        ws["remark"],
                    ),
                )

            cursor.execute(
                "INSERT OR IGNORE INTO ws_info (code, workstationType, name, capacity, section, channel, channel_code, exist, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ws["code"],
                    ws["workstationType"],
                    ws["name"],
                    bottleSlotCount,
                    section_flatten,
                    ",".join(channel_list),
                    ",".join(channel_code_list),
                    "actual",
                    ws["remark"],
                ),
            )
        conn_sql.commit()
        # -------------------------------------------------------------------

        # ----------------------bottle info-----------------------
        conn_sql.execute("BEGIN")
        for exp in task_list:
            for bottle in exp["steps"][0]["detail"]:
                cursor.execute(
                    "INSERT OR REPLACE INTO bottle_info VALUES (?, ?, ?, ?, ?)",
                    (
                        "{}_{}".format(exp["expr_no"], bottle["vials_no"]),
                        bottle["actual_no"],
                        exp["expr_no"],
                        exp["name"],
                        "starting_station",
                    ),
                )

        # Update the position; if the bottle ID is not in the table, do not update
        for ws_info in ws_list:
            for bottle in ws_info["bottleList"]:
                cursor.execute(
                    "UPDATE bottle_info SET location = ? WHERE actual_no = ?",
                    (
                        ws_info["code"],
                        bottle["bottleCode"],
                    ),
                )

        conn_sql.commit()
        # ---------------------------------------------------------

        # ----------------------Parse the task list-----------------------------------
        ws_in_highflux = []
        if len(task_list) > 0:
            conn_sql.execute("BEGIN")

            ws_in_highflux = find_ws_list_in_highflux_from_db(conn_sql)
            heating_support_magnetic = find_heating_support_magnetic(conn_sql)

            ws_name_list = list(
                set([step["workstation"] for exp in task_list for step in exp["steps"]])
            )

            add_storage_ws = any(ws_name in ws_in_highflux for ws_name in ws_name_list)
            if add_storage_ws:
                ws_name_list.append("multi_robots_exchange_workstation")
            # pprint(ws_name_list)

            ws_name_dict = {}
            for ws in ws_name_list:
                ws_name_dict[ws] = [
                    code for code in find_ws_code_list_from_db(conn_sql) if ws in code
                ]
            # pprint(ws_name_dict)

            for exp in task_list:
                expr_no = exp["expr_no"]
                expr_name = exp["name"]

                # If the task's time is null, it indicates an indeterminate time (e.g., sample introduction or liquid suction). Assign it a expected value for easier scheduling.
                fjspb_index = 0
                for i, step in enumerate(exp["steps"]):
                    ws_type = step["workstation"]
                    task_time = (
                        10
                        if ws_type == "gc"
                        else (
                            3
                            if ws_type == "fluorescence"
                            else 3 if step["time"] is None else int(step["time"])
                        )
                    )

                    # Insert a multi-robot staging station (multi_robots_exchange_workstation) before the workstation located on the high-throughput platform
                    if ws_type in ws_in_highflux:
                        ws_index = i - 1
                        ws_name = (
                            exp["steps"][ws_index]["workstation"]
                            if 0 <= ws_index < len(exp["steps"])
                            else None
                        )
                        if ws_name is not None and ws_name not in ws_in_highflux:
                            cursor.execute(
                                """
                                INSERT OR IGNORE INTO task_scheduled 
                                (b_id, fjspb_index, expr_name, expr_no, step_id, step_index, branch_code, ws_code, ws_arr, ws_code_fjspb, time, step_raw_time, detail, parameters, odd) 
                                SELECT 
                                    bi.vials_no AS b_id, 
                                    ? AS fjspb_index, 
                                    ? AS expr_name, 
                                    ? AS expr_no, 
                                    ? AS step_id, 
                                    ? AS step_index, 
                                    ? AS branch_code, 
                                    ? AS ws_code, 
                                    ? AS ws_arr, 
                                    ? AS ws_code_fjspb,
                                    ? AS time, 
                                    ? AS step_raw_time, 
                                    ? AS detail, 
                                    ? AS parameters,
                                    ? AS odd
                                FROM bottle_info AS bi
                                WHERE bi.expr_no = ?
                                """,
                                (
                                    fjspb_index,
                                    expr_name,
                                    expr_no,
                                    step["id"],
                                    step["index"],
                                    step["branch_code"],
                                    "multi_robots_exchange_workstation",
                                    "multi_robots_exchange_workstation",
                                    "multi_robots_exchange_workstation",
                                    1,
                                    None,
                                    json.dumps(
                                        {
                                            "material": None,
                                            "value": None,
                                            "material_code": None,
                                        }
                                    ),
                                    json.dumps([]),
                                    True,
                                    expr_no,
                                ),
                            )
                            fjspb_index += 1

                    if ws_type == "high_flux_electrocatalysis_workstation":
                        for one_detail in step["detail"]:
                            for oper_id, ws_name in enumerate(
                                [
                                    "high_flux_electrocatalysis_dripping",
                                    "high_flux_electrocatalysis_test",
                                    "high_flux_electrocatalysis_recycle",
                                ]
                            ):
                                cursor.execute(
                                    """
                                    INSERT OR IGNORE INTO task_scheduled 
                                    (b_id, fjspb_index, expr_name, expr_no, step_id, step_index, branch_code, ws_code, ws_arr, ws_code_fjspb, time, step_raw_time, detail, parameters) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        "{}_{}".format(expr_no, one_detail["vials_no"]),
                                        fjspb_index + oper_id,
                                        expr_name,
                                        expr_no,
                                        step["id"],
                                        step["index"],
                                        step["branch_code"],
                                        ws_name,
                                        ws_name,
                                        ws_name,
                                        (
                                            int(
                                                step["parameters"][1]["param"][
                                                    "dry_time"
                                                ]
                                            )
                                            if ws_name
                                            == "high_flux_electrocatalysis_dripping"
                                            else (
                                                40
                                                if ws_name
                                                == "high_flux_electrocatalysis_test"
                                                else 3
                                            )
                                        ),
                                        step["time"],
                                        json.dumps(one_detail),
                                        json.dumps(step["parameters"]),
                                    ),
                                )
                        fjspb_index += 3
                    elif ws_type == "high_flux_xrd_workstation":
                        for one_detail in step["detail"]:
                            for oper_id, ws_name in enumerate(
                                [
                                    "high_flux_xrd_dripping",
                                    "high_flux_xrd_test",
                                    "high_flux_xrd_recycle",
                                ]
                            ):
                                cursor.execute(
                                    """
                                    INSERT OR IGNORE INTO task_scheduled 
                                    (b_id, fjspb_index, expr_name, expr_no, step_id, step_index, branch_code, ws_code, ws_arr, ws_code_fjspb, time, step_raw_time, detail, parameters) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        "{}_{}".format(expr_no, one_detail["vials_no"]),
                                        fjspb_index + oper_id,
                                        expr_name,
                                        expr_no,
                                        step["id"],
                                        step["index"],
                                        step["branch_code"],
                                        ws_name,
                                        ws_name,
                                        ws_name,
                                        (
                                            int(
                                                step["parameters"][0]["param"][
                                                    "dry_time"
                                                ]
                                            )
                                            if ws_name == "high_flux_xrd_dripping"
                                            else (
                                                10
                                                if ws_name == "high_flux_xrd_test"
                                                else 3
                                            )
                                        ),
                                        step["time"],
                                        json.dumps(one_detail),
                                        json.dumps(step["parameters"]),
                                    ),
                                )
                        fjspb_index += 3
                    elif ws_type == "muffle_furnace":
                        for one_detail in step["detail"]:
                            cursor.execute(
                                """
                                INSERT OR IGNORE INTO task_scheduled 
                                (b_id, fjspb_index, expr_name, expr_no, step_id, step_index, branch_code, ws_code, ws_arr, ws_code_fjspb, time, step_raw_time, detail, parameters) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    "{}_{}".format(expr_no, one_detail["vials_no"]),
                                    fjspb_index,
                                    expr_name,
                                    expr_no,
                                    step["id"],
                                    step["index"],
                                    step["branch_code"],
                                    ws_type,
                                    ws_type,
                                    None,
                                    json.loads(
                                        step["parameters"][0]["param"]["custom_param"]
                                    )["time"],
                                    step["time"],
                                    json.dumps(one_detail),
                                    json.dumps(step["parameters"]),
                                ),
                            )
                        fjspb_index += 1
                    # other station
                    else:
                        merged_detail = defaultdict(
                            lambda: {
                                "material": [],
                                "value": [],
                                "vials_no": None,
                                "actual_no": None,
                                "material_code": [],
                            }
                        )
                        for item in step["detail"]:
                            vials_no = item["vials_no"]

                            matetial_info = f'{item["material"]}_{item["concentration"]}_{item["concentration_unit_code"]}'

                            merged_detail[vials_no]["material"].append(matetial_info)
                            merged_detail[vials_no]["value"].append(item["value"])
                            merged_detail[vials_no]["vials_no"] = vials_no
                            merged_detail[vials_no]["actual_no"] = item["actual_no"]
                            merged_detail[vials_no]["material_code"].append(
                                item["material_code"]
                            )

                        dispensing_ws_list = defaultdict(list)

                        # For liquid or solid dispending, find the corresponding station for the material
                        for dispense_type in ["solid_dispensing", "liquid_dispensing"]:
                            if dispense_type in ws_type:
                                for one_detail in list(merged_detail.values()):
                                    cursor.execute(
                                        """
                                        SELECT code, channel, channel_code FROM ws_info
                                        WHERE workstationType LIKE ?
                                        """,
                                        ("%" + dispense_type + "%",),
                                    )
                                    for (
                                        code,
                                        channel_str,
                                        channel_code_str,
                                    ) in cursor.fetchall():
                                        channel_vector = channel_str.split(",")
                                        if one_detail["material"][0] in channel_vector:
                                            dispensing_ws_list[
                                                one_detail["vials_no"]
                                            ].append(code)

                        for one_detail in list(merged_detail.values()):
                            cursor.execute(
                                """
                                INSERT OR IGNORE INTO task_scheduled 
                                (b_id, fjspb_index, expr_name, expr_no, step_id, step_index, branch_code, ws_code, ws_arr, ws_code_fjspb, time, step_raw_time, detail, parameters) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    "{}_{}".format(expr_no, one_detail["vials_no"]),
                                    fjspb_index,
                                    expr_name,
                                    expr_no,
                                    step["id"],
                                    step["index"],
                                    step["branch_code"],
                                    ws_type,
                                    (
                                        heating_support_magnetic
                                        if ws_type == "magnetic_stirring"
                                        and int(
                                            step["parameters"][0]["param"][
                                                "temperature"
                                            ]
                                        )
                                        >= 40
                                        else (
                                            ",".join(
                                                dispensing_ws_list[
                                                    one_detail["vials_no"]
                                                ]
                                            )
                                            if ws_type == "solid_dispensing"
                                            or ws_type == "liquid_dispensing"
                                            else ",".join(ws_name_dict[ws_type])
                                        )
                                    ),
                                    None,
                                    task_time,
                                    step["time"],
                                    json.dumps(one_detail),
                                    json.dumps(step["parameters"]),
                                ),
                            )
                        fjspb_index += 1

                    # Insert a multi-robot staging station (multi_robots_exchange_workstation) after the workstation located on the high-throughput platform
                    if ws_type in ws_in_highflux:
                        ws_index = i + 1
                        ws_name = (
                            exp["steps"][ws_index]["workstation"]
                            if 0 <= ws_index < len(exp["steps"])
                            else None
                        )
                        if ws_name is not None and ws_name not in ws_in_highflux:
                            cursor.execute(
                                """
                                INSERT OR IGNORE INTO task_scheduled 
                                (b_id, fjspb_index, expr_name, expr_no, step_id, step_index, branch_code, ws_code, ws_arr, ws_code_fjspb, time, step_raw_time, detail, parameters, odd) 
                                SELECT 
                                    bi.vials_no AS b_id, 
                                    ? AS fjspb_index, 
                                    ? AS expr_name, 
                                    ? AS expr_no, 
                                    ? AS step_id, 
                                    ? AS step_index, 
                                    ? AS branch_code, 
                                    ? AS ws_code, 
                                    ? AS ws_arr, 
                                    ? AS ws_code_fjspb,
                                    ? AS time, 
                                    ? AS step_raw_time, 
                                    ? AS detail, 
                                    ? AS parameters,
                                    ? AS odd
                                FROM bottle_info AS bi
                                WHERE bi.expr_no = ?
                                """,
                                (
                                    fjspb_index,
                                    expr_name,
                                    expr_no,
                                    step["id"],
                                    step["index"],
                                    step["branch_code"],
                                    "multi_robots_exchange_workstation",
                                    "multi_robots_exchange_workstation",
                                    "multi_robots_exchange_workstation",
                                    1,
                                    None,
                                    json.dumps(
                                        {
                                            "material": None,
                                            "value": None,
                                            "material_code": None,
                                        }
                                    ),
                                    json.dumps([]),
                                    False,
                                    expr_no,
                                ),
                            )
                            fjspb_index += 1

            conn_sql.commit()

            # Initialize the task progress mask each time, including fields such as put, take, etc., for each oper in the sequence
            # Only fields with put set to None will be initialized
            init_scheduled_table_into_db(conn_sql)

            if not flag_init_task:
                flag_init_task = True

        # ---------------------------------------------------------

        # ----------------------update bottle info -----------------------
        conn_sql.execute("BEGIN")
        if bottle_record_list:
            for record in bottle_record_list:
                if record["bottle_code"] is not None and record["status"] == "finish":
                    # If the instruction is start, dripping, test, or recycle but the actual completion time has not been reached
                    if (
                        record["operation"] != "take"
                        and record["operation"] != "put"
                        and record["time"] != None
                        and (
                            int(record["time"]) == -1
                            or (
                                int(time.time()) - int(record["finishTime"]) / 1000
                                < int(record["time"]) * 60
                            )
                        )
                    ):
                        continue
                    else:
                        if record["bottle_code"][:6] == "bottle":
                            vials_no = find_b_no_map_from_db(
                                record["bottle_code"], True, conn_sql
                            )
                        else:
                            vials_no = "{}_{}".format(
                                record["expr_no"], record["bottle_code"]
                            )
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO bottle_record 
                            (vials_no, createdTime, updatedTime, expr_no, ws_code, oper, robot, status, step_index, finish_time, time) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                vials_no,
                                record["createdTime"],
                                record["updatedTime"],
                                record["expr_no"],
                                record["workstation"],
                                record["operation"],
                                record.get("robot"),
                                record["status"],
                                record["index"],
                                (
                                    int(record["finishTime"]) / 1000
                                    if record["finishTime"] is not None
                                    else record["finishTime"]
                                ),
                                (
                                    round(record["time"])
                                    if record["time"] is not None
                                    else record["time"]
                                ),
                            ),
                        )
        conn_sql.commit()
        # ---------------------------------------------------------

        # ----------------------update bottle info real time-----------------------
        conn_sql.execute("BEGIN")
        if bottle_record_list:
            for record in bottle_record_list:
                if record["bottle_code"] is not None:
                    if record["bottle_code"][:6] == "bottle":
                        vials_no = find_b_no_map_from_db(
                            record["bottle_code"], True, conn_sql
                        )
                    else:
                        vials_no = "{}_{}".format(
                            record["expr_no"], record["bottle_code"]
                        )
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO bottle_record_real 
                        (vials_no, createdTime, updatedTime, expr_no, ws_code, oper, robot, status, step_index, finish_time, time) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            vials_no,
                            record["createdTime"],
                            record["updatedTime"],
                            record["expr_no"],
                            record["workstation"],
                            record["operation"],
                            record.get("robot"),
                            record["status"],
                            record["index"],
                            (
                                int(record["finishTime"]) / 1000
                                if record["finishTime"] is not None
                                else record["finishTime"]
                            ),
                            (
                                round(record["time"])
                                if record["time"] is not None
                                else record["time"]
                            ),
                        ),
                    )
        conn_sql.commit()
        # ---------------------------------------------------------

        # ----------------------update task database-----------------------
        conn_sql.execute("BEGIN")

        cursor.execute(
            "SELECT vials_no, oper, robot, step_index, updatedTime, createdTime, finish_time, time FROM bottle_record"
        )
        for (
            vials_no,
            oper,
            robot_name,
            step_index,
            updated_time,
            created_time,
            finish_time,
            task_time,
        ) in cursor.fetchall():
            if oper == "take" or oper == "put":
                cursor.execute(
                    f"UPDATE task_scheduled SET {oper} = True, {oper}_robot = ?, {oper}_create_time = ?, {oper}_finish_time = ? WHERE b_id = ? AND fjspb_index = ?",
                    (
                        robot_name,
                        created_time,
                        updated_time,
                        vials_no,
                        step_index,
                    ),
                )
            else:
                cursor.execute(
                    f"UPDATE task_scheduled SET {oper} = True, {oper}_create_time = ?, {oper}_finish_time = ?, record_time = ? WHERE b_id = ? AND fjspb_index = ?",
                    (
                        created_time,
                        updated_time,
                        task_time,
                        vials_no,
                        step_index,
                    ),
                )

        conn_sql.commit()
        # ---------------------------------------------------------

        # ------------------Update whether the tasks have been scheduled based on cur_ws_ptr---------------
        conn_sql.execute("BEGIN")

        cursor.execute("SELECT * FROM task_scheduled")
        column_names = [description[0] for description in cursor.description]
        for row in cursor.fetchall():
            row_data = dict(zip(column_names, row))
            if (
                row_data["start_time"] is not None
                and row_data["start_time"] < cur_ws_ptr
            ):
                cursor.execute(
                    """
                    UPDATE task_scheduled 
                    SET has_scheduled = ? 
                    WHERE b_id = ? AND fjspb_index = ?""",
                    (True, row_data["b_id"], row_data["fjspb_index"]),
                )
        conn_sql.commit()
        # ---------------------------------------------------------

    except sqlite3.Error as e:
        conn_sql.rollback()
        print("Error: ", e)

    ws_in_highflux = find_ws_list_in_highflux_from_db(conn_sql)

    return flag_init_task, ws_in_highflux


def construct_fjspb_jobs_data_from_db(conn_sql: sqlite3.Connection) -> dict:
    cursor = conn_sql.cursor()
    cursor.execute(
        """
        SELECT b_id, ws_arr, time, parameters, has_scheduled, start_time, end,ws_code_fjspb 
        FROM task_scheduled 
        ORDER BY fjspb_index"""
    )
    jobs_data = defaultdict(list)
    for (
        b_id,
        ws_arr,
        task_time,
        parameters,
        has_scheduled,
        start_time,
        end,
        ws_code_fjspb,
    ) in cursor.fetchall():
        if has_scheduled is not None and has_scheduled == True:
            ws_arr_list = [ws_code_fjspb]
        else:
            ws_arr_list = ws_arr.split(",")

        jobs_data[b_id].append(
            (
                ws_arr_list,
                task_time,
                json.loads(parameters),
                {
                    "has_scheduled": has_scheduled,
                    "start_time": start_time,
                    "end": end,
                    "ws_code_fjspb": ws_code_fjspb,
                },
            )
        )
    return jobs_data


# Complete the attributes of the task table in the database
def init_scheduled_table_into_db(conn_sql: sqlite3.Connection):
    cursor = conn_sql.cursor()
    try:
        conn_sql.execute("BEGIN")

        cursor.execute("SELECT * FROM task_scheduled")
        column_names = [description[0] for description in cursor.description]
        for row in cursor.fetchall():
            row_data = dict(zip(column_names, row))
            # If it is the starting station and the first sequence, no put or start operation is needed
            if (
                row_data["ws_code"] == "starting_station"
                and row_data["fjspb_index"] == 0
            ):
                put, start = True, True
            else:
                put, start = False, False

            if row_data["put"] is None:
                cursor.execute(
                    """
                    UPDATE task_scheduled 
                    SET put = ?, take = ?, start = ?,
                        electronic_dripping = ?,
                        electronic_test = ?,
                        electronic_recycle = ?,
                        xrd_dripping = ?,
                        xrd_test = ?,
                        xrd_recycle = ?
                    WHERE b_id = ? AND fjspb_index = ?
                    """,
                    (
                        put,
                        False,
                        start,
                        False,
                        False,
                        False,
                        False,
                        False,
                        False,
                        row_data["b_id"],
                        row_data["fjspb_index"],
                    ),
                )

        conn_sql.commit()
    except sqlite3.Error as e:
        conn_sql.rollback()

    return


# Retrieve the return value from the database based on ws_code
def find_capacity_by_ws_code_from_db(code: str, conn_sql: sqlite3.Connection) -> int:
    cursor = conn_sql.cursor()
    cursor.execute("SELECT capacity FROM ws_info WHERE code = ?", (code,))
    result = cursor.fetchone()
    return result[0] if result else 0


# Retrieve all ws_code values from the database
def find_ws_code_list_from_db(conn_sql: sqlite3.Connection) -> list:
    cursor = conn_sql.cursor()
    cursor.execute(f"SELECT code FROM ws_info")
    ws_codes = [row[0] for row in cursor.fetchall()]
    return ws_codes


# Retrieve all ws_code values for high-throughput workstations from the database
def find_ws_list_in_highflux_from_db(conn_sql: sqlite3.Connection) -> list:
    cursor = conn_sql.cursor()
    cursor.execute("SELECT code, section FROM ws_info")
    ws_in_highflux = []
    for code, section in cursor.fetchall():
        if (
            code != "storage_workstation"
            and code != "multi_robots_exchange_workstation"
            and "highflux-platform" in section
        ):
            ws_in_highflux.append(code)
    return ws_in_highflux


# Based on the global pointer and the task progress table in the database, find the sequence of operations to be executed at the current pointer
def find_matching_tasks_from_db(ws_ptr, conn_sql: sqlite3.Connection):
    cursor = conn_sql.cursor()
    cursor.execute("SELECT * FROM task_scheduled")
    column_names = [description[0] for description in cursor.description]

    matching_tasks = defaultdict(lambda: defaultdict(list))
    for row in cursor.fetchall():
        row_data = dict(zip(column_names, row))
        ws_code = row_data["ws_code_fjspb"]

        if ws_code == "high_flux_electrocatalysis_dripping":
            if row_data["start_time"] == ws_ptr:
                if not row_data["put"]:
                    matching_tasks["do_put"][ws_code].append(row_data)
                if not row_data["electronic_dripping"]:
                    matching_tasks["do_dripping"][ws_code].append(row_data)
        elif ws_code == "high_flux_electrocatalysis_test":
            if row_data["start_time"] == ws_ptr and not row_data["electronic_test"]:
                matching_tasks["do_test"][ws_code].append(row_data)
        elif ws_code == "high_flux_electrocatalysis_recycle":
            if row_data["start_time"] == ws_ptr and not row_data["electronic_recycle"]:
                matching_tasks["do_recycle"][ws_code].append(row_data)
            if row_data["end"] == ws_ptr and not row_data["take"]:
                matching_tasks["do_take"][ws_code].append(row_data)
        elif ws_code == "high_flux_xrd_dripping":
            if row_data["start_time"] == ws_ptr:
                if not row_data["put"]:
                    matching_tasks["do_put"][ws_code].append(row_data)
                if not row_data["xrd_dripping"]:
                    matching_tasks["do_dripping"][ws_code].append(row_data)
        elif ws_code == "high_flux_xrd_test":
            if row_data["start_time"] == ws_ptr and not row_data["xrd_test"]:
                matching_tasks["do_test"][ws_code].append(row_data)
        elif ws_code == "high_flux_xrd_recycle":
            if row_data["start_time"] == ws_ptr and not row_data["xrd_recycle"]:
                matching_tasks["do_recycle"][ws_code].append(row_data)
            if row_data["end"] == ws_ptr and not row_data["take"]:
                matching_tasks["do_take"][ws_code].append(row_data)
        else:
            # other station
            if row_data["start_time"] == ws_ptr:
                if not row_data["put"]:
                    matching_tasks["do_put"][ws_code].append(row_data)
                if not row_data["start"]:
                    matching_tasks["do_start"][ws_code].append(row_data)
            if row_data["end"] == ws_ptr and not row_data["take"]:
                if (
                    row_data["fjspb_index"] + 1 == row_data["job_length"]
                    and row_data["ws_code"] == "starting_station"
                ):
                    pass
                else:
                    matching_tasks["do_take"][ws_code].append(row_data)

        # Tasks immediately to the left of the current pointer, used to ensure that all previous steps are completed before performing the "take" operation
        if row_data["end"] == ws_ptr:
            matching_tasks["left"][row_data["ws_code_fjspb"]].append(row_data)

    return matching_tasks


# Retrieve all bottle positions from the database and return them as a dictionary
def find_bottle_location_from_db(conn_sql: sqlite3.Connection) -> dict:
    cursor = conn_sql.cursor()
    cursor.execute("SELECT vials_no, location FROM bottle_info")
    location_dict = dict(cursor.fetchall())
    return location_dict


# Find the mapping between virtual and actual bottle numbers
def find_b_no_map_from_db(
    src_no: str, actual_to_vials: bool, conn_sql: sqlite3.Connection
) -> str:
    cursor = conn_sql.cursor()
    if actual_to_vials:
        cursor.execute(
            "SELECT vials_no FROM bottle_info where actual_no = ?", (src_no,)
        )
    else:
        cursor.execute(
            "SELECT actual_no FROM bottle_info where vials_no = ?", (src_no,)
        )
    dis_no = cursor.fetchone()
    return dis_no[0] if dis_no else ""


# Parse the experimental steps
def find_expr_no_to_steps_from_db(conn_sql: sqlite3.Connection) -> dict:
    cursor = conn_sql.cursor()
    cursor.execute(
        """
        SELECT expr_no, step_id, step_index, branch_code 
        FROM task_scheduled
        WHERE step_id NOT GLOB '*[a-zA-Z]*'
        """
    )

    expr_no_to_steps = defaultdict(dict)
    for expr_no, step_id, step_index, branch_code in cursor.fetchall():
        expr_no_to_steps[expr_no][step_index] = {
            "step_id": step_id,
            "branch_code": branch_code,
        }

    return expr_no_to_steps


# Retrieve task information based on the primary key (b_id, fjspb_index)
def fetch_task_info_from_db(
    b_id, fjspb_index, conn_sql: sqlite3.Connection, full_info=False
):
    cursor = conn_sql.cursor()
    cursor.execute(
        """
        SELECT * FROM task_scheduled
        WHERE b_id = ? AND fjspb_index = ?
        """,
        (
            b_id,
            fjspb_index,
        ),
    )
    column_names = [description[0] for description in cursor.description]
    row = cursor.fetchone()
    task_data = dict(zip(column_names, row))

    if full_info:
        return task_data
    else:
        task_info = {
            "expr_no": task_data["expr_no"],
            "expr_name": task_data["expr_name"],
            "step_id": task_data["step_id"],
            "fjspb_index": task_data["fjspb_index"],
            "step_index": task_data["step_index"],
            "step_raw_time": task_data["step_raw_time"],
            "detail": json.loads(task_data["detail"]),
            "parameters": json.loads(task_data["parameters"]),
        }
        return task_info


# Find all magnetic stirrers with heating functionality
def find_heating_support_magnetic(conn_sql: sqlite3.Connection):
    cursor = conn_sql.cursor()
    cursor.execute(
        """
        SELECT code FROM ws_info
        WHERE remark = ?
        """,
        ("heating_support",),
    )
    rows = cursor.fetchall()
    code_string = ",".join([row[0] for row in rows])
    return code_string


# Retrieve the battery level and status of the robots
def find_robot_status(robot_code, conn_sql: sqlite3.Connection):
    cursor = conn_sql.cursor()
    cursor.execute(
        """
        SELECT status, electricityQuantity FROM robot_info
        WHERE code = ?
        """,
        (robot_code,),
    )
    row = cursor.fetchone()
    return row[0], row[1]


def check_bottle_records(one_assign, conn_sql: sqlite3.Connection):
    cursor = conn_sql.cursor()

    query_record_real = """
    SELECT * FROM bottle_record_real
    WHERE vials_no = ?
    AND step_index = ?
    AND oper = ?
    AND robot = ?
    AND ws_code = ?
    """

    params = []
    for bottle_msg in one_assign["bottleList"]:
        if bottle_msg["bottleCode"][:6] == "bottle":
            vials_no = find_b_no_map_from_db(bottle_msg["bottleCode"], True, conn_sql)
        else:
            vials_no = "{}_{}".format(bottle_msg["expr_no"], bottle_msg["bottleCode"])

        if vials_no:
            params.append(
                (
                    vials_no,
                    bottle_msg["index"],
                    one_assign["operation"],
                    one_assign["robot"],
                    one_assign["workstation"],
                )
            )

    for param in params:
        cursor.execute(query_record_real, param)
        result = cursor.fetchone()
        if result:
            cursor.close()
            return True

    cursor.close()
    return False
