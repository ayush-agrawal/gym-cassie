from .envs import CassieEnv
from gym.envs.registration import register

register(
    id='Cassie-v0',
    entry_point='gym_cassie.envs.cassie_env:CassieEnv',
)

register(
    id='Cassie-mimic-v0',
    entry_point='gym_cassie.envs:CassieMimicEnv',
)

register(
    id='Cassie-mimic-walking-v0',
    entry_point='gym_cassie.envs:CassieMimicEnv',
    kwargs={'traj': 'walking'}
)