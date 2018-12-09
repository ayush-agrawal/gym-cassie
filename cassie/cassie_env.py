from .cassiemujoco import pd_in_t, CassieSim, CassieVis

from .trajectory import CassieTrajectory

from math import floor

import numpy as np 
import os
import random

#import pickle

class CassieEnv:
    def __init__(self, traj_path, simrate=60, clock_based=False):
        self.sim = CassieSim()
        self.vis = None

        self.clock_based = clock_based

        if clock_based:
            self.observation_space = np.zeros(42)
            self.action_space      = np.zeros(10)
        else:
            self.observation_space = np.zeros(80)
            self.action_space      = np.zeros(10)

        self.trajectory = CassieTrajectory(traj_path)

        self.P = np.array([100,  100,  88,  96,  50])
        self.D = np.array([10.0, 10.0, 8.0, 9.6, 5.0])

        self.u = pd_in_t()

        self.simrate = simrate # simulate X mujoco steps with same pd target
                               # 60 brings simulation from 2000Hz to roughly 30Hz

        self.time    = 0 # number of time steps in current episode
        self.phase   = 0 # portion of the phase the robot is in
        self.counter = 0 # number of phase cycles completed in episode

        # NOTE: a reference trajectory represents ONE phase cycle

        # should be floor(len(traj) / simrate) - 1
        # should be VERY cautious here because wrapping around trajectory
        # badly can cause assymetrical/bad gaits
        self.phaselen = floor(len(self.trajectory) / self.simrate) - 1

        self.time_limit = 400

        # see include/cassiemujoco.h for meaning of these indices
        self.pos_idx = [7, 8, 9, 14, 20, 21, 22, 23, 28, 34]
        self.vel_idx = [6, 7, 8, 12, 18, 19, 20, 21, 25, 31]
    
        #self.name = 

    def step_simulation(self, action):

        # maybe make ref traj only send relevant idxs?
        ref_pos, ref_vel = self.get_ref_state(self.phase)

        target = action + ref_pos[self.pos_idx]

        self.u = pd_in_t()
        for i in range(5):
            # TODO: move setting gains out of the loop?
            # maybe write a wrapper for pd_in_t ?
            self.u.leftLeg.motorPd.pGain[i]  = self.P[i]
            self.u.rightLeg.motorPd.pGain[i] = self.P[i]

            self.u.leftLeg.motorPd.dGain[i]  = self.D[i]
            self.u.rightLeg.motorPd.dGain[i] = self.D[i]

            self.u.leftLeg.motorPd.torque[i]  = 0 # Feedforward torque
            self.u.rightLeg.motorPd.torque[i] = 0 

            self.u.leftLeg.motorPd.pTarget[i]  = target[i]
            self.u.rightLeg.motorPd.pTarget[i] = target[i + 5]

            self.u.leftLeg.motorPd.dTarget[i]  = 0
            self.u.rightLeg.motorPd.dTarget[i] = 0

        self.sim.step_pd(self.u)

    def step(self, action):
        for _ in range(self.simrate):
            self.step_simulation(action)

        height = self.sim.qpos()[2]

        self.time  += 1
        self.phase += 1

        if self.phase > self.phaselen:
            self.phase = 0
            self.counter += 1

        # Early termination
        done = not(height > 0.4 and height < 3.0) or self.time >= self.time_limit

        reward = self.compute_reward()

        # TODO: make 0.3 a variable/more transparent
        if reward < 0.3:
            done = True

        return self.get_full_state(), reward, done, {}

    def reset(self):
        self.phase = random.randint(0, self.phaselen)
        self.time = 0
        self.counter = 0

        qpos, qvel = self.get_ref_state(self.phase)

        self.sim.set_qpos(qpos)
        self.sim.set_qvel(qvel)

        return self.get_full_state()

    def compute_reward(self):
        qpos = np.copy(self.sim.qpos())

        ref_pos, ref_vel = self.get_ref_state(self.phase)

        # TODO: should be variable; where do these come from?
        # TODO: see magnitude of state variables to gauge contribution to reward
        weight = [0.15, 0.15, 0.1, 0.05, 0.05, 0.15, 0.15, 0.1, 0.05, 0.05]

        joint_error       = 0
        com_error         = 0
        orientation_error = 0
        spring_error      = 0

        # each joint pos
        for i, j in enumerate(self.pos_idx):
            target = ref_pos[j]
            actual = qpos[j]

            joint_error += 30 * weight[i] * (target - actual) ** 2

        # center of mass: x, y, z
        for j in [0, 1, 2]:
            target = ref_pos[j]
            actual = qpos[j]

            com_error += (target - actual) ** 2
        
        # COM orientation: qx, qy, qz
        for j in [4, 5, 6]:
            target = ref_pos[j]
            actual = qpos[j]

            orientation_error += (target - actual) ** 2

        # left and right shin springs
        for i in [15, 28]:
            target = ref_pos[i]
            actual = qpos[i]

            spring_error += 1000 * (target - actual) ** 2      
        
        reward = 0.5 * np.exp(-joint_error) +       \
                 0.3 * np.exp(-com_error) +         \
                 0.1 * np.exp(-orientation_error) + \
                 0.1 * np.exp(-spring_error)


        # orientation error does not look informative
        # maybe because it's comparing euclidean distance on quaternions
        # print("reward: {8}\njoint:\t{0:.2f}, % = {1:.2f}\ncom:\t{2:.2f}, % = {3:.2f}\norient:\t{4:.2f}, % = {5:.2f}\nspring:\t{6:.2f}, % = {7:.2f}\n\n".format(
        #             0.5 * np.exp(-joint_error),       0.5 * np.exp(-joint_error) / reward * 100,
        #             0.3 * np.exp(-com_error),         0.3 * np.exp(-com_error) / reward * 100,
        #             0.1 * np.exp(-orientation_error), 0.1 * np.exp(-orientation_error) / reward * 100,
        #             0.1 * np.exp(-spring_error),      0.1 * np.exp(-spring_error) / reward * 100,
        #             reward
        #         )
        #     )  

        return reward

    # get the corresponding state from the reference trajectory for the current phase
    def get_ref_state(self, phase=None):
        if phase is None:
            phase = self.phase

        if phase >= self.phaselen:
            phase = 0

        pos = np.copy(self.trajectory.qpos[phase * self.simrate])

        # this is just setting the x to where it "should" be given the number
        # of cycles?
        pos[0] += (self.trajectory.qpos[-1, 0] - self.trajectory.qpos[0, 0]) * self.counter
        
        # ^ should only matter for COM error calculation,
        # gets dropped out of state variable for input reasons

        # setting lateral distance target to 0?
        # regardless of reference trajectory?
        pos[1] = 0

        vel = np.copy(self.trajectory.qvel[phase * self.simrate])

        return pos, vel

    def get_full_state(self):
        qpos = np.copy(self.sim.qpos())
        qvel = np.copy(self.sim.qvel()) 

        ref_pos, ref_vel = self.get_ref_state(self.phase + 1)

        # TODO: maybe convert to set subtraction for clarity
        # {i for i in range(35)} - 
        # {0, 10, 11, 12, 13, 17, 18, 19, 24, 25, 26, 27, 31, 32, 33}

        # this is everything except pelvis x and qw, achilles rod quaternions, 
        # and heel spring/foot crank/plantar rod angles
        # note: x is forward dist, y is lateral dist, z is height

        # makes sense to always exclude x because it is in global coordinates and
        # irrelevant to phase-based control. Z is inherently invariant to
        # trajectory despite being global coord. Y is only invariant to straight
        # line trajectories.

        # [ 0] Pelvis y
        # [ 1] Pelvis z
        # [ 2] Pelvis orientation qw
        # [ 3] Pelvis orientation qx
        # [ 4] Pelvis orientation qy
        # [ 5] Pelvis orientation qz
        # [ 6] Left hip roll         (Motor [0])
        # [ 7] Left hip yaw          (Motor [1])
        # [ 8] Left hip pitch        (Motor [2])
        # [ 9] Left knee             (Motor [3])
        # [10] Left shin                        (Joint [0])
        # [11] Left tarsus                      (Joint [1])
        # [12] Left foot             (Motor [4], Joint [2])
        # [13] Right hip roll        (Motor [5])
        # [14] Right hip yaw         (Motor [6])
        # [15] Right hip pitch       (Motor [7])
        # [16] Right knee            (Motor [8])
        # [17] Right shin                       (Joint [3])
        # [18] Right tarsus                     (Joint [4])
        # [19] Right foot            (Motor [9], Joint [5])

        pos_index = np.array([1,2,3,4,5,6,7,8,9,14,15,16,20,21,22,23,28,29,30,34])

        # [ 0] Pelvis x
        # [ 1] Pelvis y
        # [ 2] Pelvis z
        # [ 3] Pelvis orientation wx
        # [ 4] Pelvis orientation wy
        # [ 5] Pelvis orientation wz
        # [ 6] Left hip roll         (Motor [0])
        # [ 7] Left hip yaw          (Motor [1])
        # [ 8] Left hip pitch        (Motor [2])
        # [ 9] Left knee             (Motor [3])
        # [10] Left shin                        (Joint [0])
        # [11] Left tarsus                      (Joint [1])
        # [12] Left foot             (Motor [4], Joint [2])
        # [13] Right hip roll        (Motor [5])
        # [14] Right hip yaw         (Motor [6])
        # [15] Right hip pitch       (Motor [7])
        # [16] Right knee            (Motor [8])
        # [17] Right shin                       (Joint [3])
        # [18] Right tarsus                     (Joint [4])
        # [19] Right foot            (Motor [9], Joint [5])
        vel_index = np.array([0,1,2,3,4,5,6,7,8,12,13,14,18,19,20,21,25,26,27,31])

        ext_state = np.concatenate([ref_pos[pos_index], ref_vel[vel_index]])

        if self.clock_based:
            qpos[pos_idx] -= ref_pos[pos_idx]
            qvel[vel_idx] -= ref_vel[vel_idx]

            clock = [np.sin(2 * np.pi *  self.phase / self.phaselen),
                     np.cos(2 * np.pi *  self.phase / self.phaselen)]


        return np.concatenate([qpos[pos_index], 
                               qvel[vel_index], 
                               ext_state])

    def render(self):
        if self.vis is None:
            self.vis = CassieVis()

        self.vis.draw(self.sim)
