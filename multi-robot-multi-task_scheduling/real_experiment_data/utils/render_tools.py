import sqlite3
import json
import time

from collections import defaultdict


def construct_real_data_from_db(conn_sql: sqlite3.Connection) -> dict:
    cursor = conn_sql.cursor()
    cursor.execute(
        """
        SELECT b_id, ws_arr, time, parameters, ws_code_fjspb 
        FROM task_scheduled 
        ORDER BY fjspb_index"""
    )
    jobs_data = defaultdict(list)
    for (
        b_id,
        ws_arr,
        task_time,
        parameters,
        ws_code_fjspb,
    ) in cursor.fetchall():
        ws_arr_list = ws_arr.split(",")
        jobs_data[b_id].append(
            (
                ws_arr_list,
                task_time,
                json.loads(parameters),
                {
                    "ws_code_fjspb": ws_code_fjspb,
                },
            )
        )
    return jobs_data
