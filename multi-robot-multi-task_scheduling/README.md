# Multi-robot-multi-task scheduling module

## Directory tree
> + hello_world_example
>   + A simple example with the minimum number of workstations and the shortest task length.
> + simulaton_methods
>   + Code folder for generate simulation result.
> + real_experiment_data
>   + A folder containing real experimental data along with the configured rendering code.
> + README.md

The core algorithm code for multi-task scheduling, namely FESP-B, can be found in [fespb.py](./hello_world_example/fespb/fespb.py). The code [multi_robot_multi_task_scheduling.py](./hello_world_example/scheduling.py) integrates the scheduling results of the FESP-B algorithm and considers the lab status for the scheduling of robots and stations, thus forming the multi-robot-multi-task scheduling module.

## Dependences

### Constraints Programming Solver
Download the [IBM ILOG CPLEX solver](https://www.ibm.com/products/ilog-cplex-optimization-studio/cplex-optimizer) . An academic free version can be found [here](https://www.ibm.com/academic). Follow the software instructions to complete the installation and set up the environment variables.

### Python Library
```python
python3 -m pip install -r requirements.txt
```

## Document
Detailed instructions on how to explore each folder can be found in the README.md file within each folder.

## hello_world_example
[hello-world-README.md](./hello_world_example/README.md)

## simulaton_methods
[simulation-README.md](./simulation_methods/README.md)

## real_experiment_data
[real-experiments-README.md](./real_experiment_data/README.md)