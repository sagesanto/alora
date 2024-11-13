from ortools.sat.python import cp_model
import pandas as pd, numpy as np

# this is an attempt at a constraint-based scheduler using google OR-Tools. it has problems so i'm moving on to a different approach

class object:
    def __init__(self, d, r, w, f, scores):
        self.d = d
        self.r = r
        self.w = w
        self.f = f
        self.scores = scores

# constraints when scheduling observation of object A of duration d with 
# r required repeat obs with a wait time of w between each observation
# and a minimum time since last focus loop of f
# 1. the observation must start between the start and end of the night
# 2. the observation must end before the end of the night
# 3. if A is scheduled, the subsequent d slots must all have A in their domain (observability constraint)
# 4. if A is scheduled, the subsequent d slots must all be blocked off (no collisions)
# 5. if A is scheduled, r d-length consecutive observations of A must subsequently be scheduled with w slots between each observation
# 6. A cannot be scheduled within w slots of the last START TIME of A
# 7. A must be scheduled exactly r+1 times or not at all
# 8. A must END within f slots of the last focus loop
# 9. if A is scheduled, it must be scheduled for the full duration d

# constraints when scheduling focus loops
# 1. the focus loop must start between the start and end of the night
# 2. the focus loop must end before the end of the night
# 3. cocus loops can be scheduled at any unoccupied time
# 4. focus loops last for a fixed duration and cannot be interrupted

# observations may have different durations, but they must all be multiples of the time resolution
# observations may or may not have non-zero r
# observations may or may not have non-zero w
# observations with f=-1 are not subject to the focus loop constraint

# optimization:
# each object comes with an array of scores, one for each time slot. we want to maximize the sum of the scores of the slots we schedule
# focus loops have a score of 0
# if objects have r > 0, their different observations may have different scores. scoring must take this into account and use the correct scoring array depending on which instance of the object is being scheduled

# if an object has a score of 0 at a given time slot, it is not visible at that time - it is not in the domain of that time slot
num_objects = 3

loaded_scores = pd.read_csv("arrayDf.csv")
objects = []
for i in range(num_objects):
    objects.append(object(1, 1, 1, 1, np.insert(loaded_scores.iloc[i][1:].to_numpy(),0,0)))

timeResolution = 1
slots = np.arange(0, len(loaded_scores.iloc[0][1:])+1, timeResolution)

# print(objects[0].scores)

model = cp_model.CpModel()

# variables
# obs_start_times[i, j] is the start time of the jth observation of object i
obs_start_times = {}
for i in range(num_objects):
    for j in range(objects[i].r + 1):
        obs_start_times[i, j] = model.NewIntVar(0, len(slots), f'obs_start_times[{i},{j}]')
print(obs_start_times)

# obs_end_times[i, j] is the end time of the jth observation of object i
obs_end_times = {}
for i in range(num_objects):
    for j in range(objects[i].r + 1):
        obs_end_times[i, j] = model.NewIntVar(0, len(slots), f'obs_end_times[{i},{j}]')
print(obs_end_times)

# focus_start_times[i] is the start time of the ith focus loop
focus_start_times = {}
for i in range(len(objects)+1):
    focus_start_times[i] = model.NewIntVar(0, len(slots), f'focus_start_times[{i}]')

# focus_end_times[i] is the end time of the ith focus loop
focus_end_times = {}
for i in range(len(objects)+1):
    focus_end_times[i] = model.NewIntVar(0, len(slots), f'focus_end_times[{i}]')

# constraints
# 1. the observation must start between the start and end of the night
# 2. the observation must end before the end of the night
for i in range(num_objects):
    for j in range(objects[i].r + 1):
        model.Add(obs_start_times[i, j] >= 0)
        model.Add(obs_start_times[i, j] <= len(slots))
        model.Add(obs_end_times[i, j] >= 0)
        model.Add(obs_end_times[i, j] <= len(slots))

# 3. A can only be scheduled if the subsequent d slots all have A in their domain (i.e. the score at that slot is non-zero) (observability constraint)
for i, obj in enumerate(objects):
    for j in range(obj.r + 1):
        for k in range(len(slots)):
            model.Add(obs_start_times[i, j] != k).OnlyEnforceIf([bool(obj.scores[k] == 0)])

# create a 2D list to store the is_obs_start_non_zero variables
is_obs_start_non_zero = [[None for _ in range(obj.r + 1)] for obj in objects]

# an observation must end exactly d slots after it starts
for i, obj in enumerate(objects):
    for j in range(obj.r + 1):
        is_obs_start_non_zero[i][j] = model.NewBoolVar(f'is_obs_start_non_zero[{i},{j}]')
        model.Add(obs_start_times[i, j] != 0).OnlyEnforceIf(is_obs_start_non_zero[i][j])
        model.Add(obs_end_times[i, j] == obs_start_times[i, j] + obj.d).OnlyEnforceIf(is_obs_start_non_zero[i][j])

# no observation can be scheduled between the start and end times of another observation (no collisions)
for i, obj in enumerate(objects):
    for j in range(obj.r + 1):
        for k in range(i, num_objects):
            for l in range(objects[k].r + 1):
                # 0 is our placeholder value for an unoccupied slot, so we need to avoid constraining it
                model.Add(obs_start_times[i, j] >= obs_end_times[k, l]).OnlyEnforceIf(is_obs_start_non_zero[i][j])
                model.Add(obs_end_times[i, j] <= obs_start_times[k, l]).OnlyEnforceIf(is_obs_start_non_zero[i][j])


# 5. if A is scheduled, r d-length consecutive observations of A must subsequently be scheduled with w slots between each observation
# 6. A cannot be scheduled within w slots of the last START TIME of A
for i, obj in enumerate(objects):
    for j in range(obj.r):
        model.Add(obs_start_times[i, j + 1] == obs_end_times[i, j] + obj.w)

# 7. A must be scheduled exactly r+1 times or not at all
for i, obj in enumerate(objects):
    # create a list of IntVar objects
    obs_start_times_non_zero = [model.NewIntVar(0, 1, f'obs_start_times_non_zero[{i},{j}]') for j in range(obj.r + 1)]
    
    # add constraints that each obs_start_times_non_zero[i, j] is equal to whether obs_start_times[i, j] is not zero
    for j in range(obj.r + 1):
        model.Add(obs_start_times[i, j] != 0).OnlyEnforceIf(obs_start_times_non_zero[j])
        model.Add(obs_start_times[i, j] == 0).OnlyEnforceIf(obs_start_times_non_zero[j].Not())
    
    # create a new Boolean variable that is true if and only if sum(obs_start_times_non_zero) > 0
    sum_obs_start_times_non_zero_gt_0 = model.NewBoolVar('sum_obs_start_times_non_zero_gt_0')
    model.Add(sum(obs_start_times_non_zero) > 0).OnlyEnforceIf(sum_obs_start_times_non_zero_gt_0)
    model.Add(sum(obs_start_times_non_zero) <= 0).OnlyEnforceIf(sum_obs_start_times_non_zero_gt_0.Not())
    
    # add the constraint to the model
    model.Add(sum(obs_start_times_non_zero) == obj.r + 1).OnlyEnforceIf(sum_obs_start_times_non_zero_gt_0)
    model.Add(sum(obs_start_times_non_zero) == 0).OnlyEnforceIf(sum_obs_start_times_non_zero_gt_0.Not())

# # 8. A must END within f slots of the last focus loop
# for i, obj in enumerate(objects):
#     for j in range(obj.r + 1):
#         model.Add(obs_end_times[i, j] <= focus_end_times[i] + obj.f)

# focus loop constraints
# 1. the focus loop must start between the start and end of the night
# 2. the focus loop must end before the end of the night
# for i in range(len(objects)+1):
#     model.Add(focus_start_times[i] >= 0)
#     model.Add(focus_start_times[i] <= len(slots))
#     model.Add(focus_end_times[i] >= 0)
#     model.Add(focus_end_times[i] <= len(slots))

# 3. focus loops can be scheduled at any unoccupied time

# # 4. focus loops last for a fixed duration and cannot be interrupted
# for i in range(len(objects)+1):
#     model.Add(focus_end_times[i] == focus_start_times[i] + 1)

# # 5. no focus loop can be scheduled during an observation
# for i, obj in enumerate(objects):
#     for j in range(obj.r + 1):
#         model.Add(focus_start_times[i] >= obs_end_times[i, j])
#         model.Add(focus_end_times[i] <= obs_start_times[i, j + 1])

# # 6. no observation can be scheduled during a focus loop
# for i in range(len(objects)+1):
#     for j in range(len(objects)+1):
#         model.Add(obs_start_times[i, j] >= focus_end_times[i])
#         model.Add(obs_end_times[i, j] <= focus_start_times[i + 1])
    
# run the model
solver = cp_model.CpSolver()
status = solver.Solve(model)
print(status)
if status == cp_model.OPTIMAL:
    print('Solution found')
    for i in range(num_objects):
        for j in range(objects[i].r + 1):
            print(f'object {i} observation {j} starts at {solver.Value(obs_start_times[i, j])} and ends at {solver.Value(obs_end_times[i, j])}')
    for i in range(len(objects)+1):
        print(f'focus loop {i} starts at {solver.Value(focus_start_times[i])} and ends at {solver.Value(focus_end_times[i])}')