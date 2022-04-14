from ray import tune
from ray.tune.utils import merge_dicts
from ray.rllib.agents.a3c.a3c_tf_policy import A3CTFPolicy
from ray.rllib.agents.a3c.a3c_torch_policy import A3CTorchPolicy
from ray.rllib.agents.a3c.a2c import A2CTrainer
from ray.rllib.agents.a3c.a2c import A2C_DEFAULT_CONFIG as A2C_CONFIG
from SMAC.util.mappo_tools import *
from SMAC.util.maa2c_tools import *


def run_maa2c(args, common_config, env_config, stop, reporter):
    obs_shape = env_config["obs_shape"]
    n_ally = env_config["n_ally"]
    n_enemy = env_config["n_enemy"]
    state_shape = env_config["state_shape"]
    n_actions = env_config["n_actions"]
    episode_limit = env_config["episode_limit"]

    episode_num = 10
    train_batch_size = episode_num * episode_limit
    # This is for compensate the RLLIB optimization style, even if
    # we use share policy, rllib will split it into agent number iteration
    # which means, compared to optimization like pymarl (homogeneous),
    # the batchsize is reduced as b * 1/agent_num.
    if args.share_policy:
        train_batch_size *= n_ally

    config = {
        "env": "smac",
        "batch_mode": "complete_episodes",
        "train_batch_size": train_batch_size,
        "lr": 0.0005,
        "entropy_coeff": 0.01,
        "model": {
            "custom_model": "{}_CentralizedCritic".format(args.neural_arch),
            "max_seq_len": episode_limit,
            "custom_model_config": {
                "token_dim": args.token_dim,
                "ally_num": n_ally,
                "enemy_num": n_enemy,
                "self_obs_dim": obs_shape,
                "state_dim": state_shape
            },
        },
    }
    config.update(common_config)

    MAA2C_CONFIG = merge_dicts(
        A2C_CONFIG,
        {
            "agent_num": n_ally,
            "state_dim": state_shape,
            "self_obs_dim": obs_shape,
            "centralized_critic_obs_dim": -1,
        }
    )

    MAA2CTFPolicy = A3CTFPolicy.with_updates(
        name="MAA2CTFPolicy",
        postprocess_fn=centralized_critic_postprocessing,
        loss_fn=loss_with_central_critic_a2c,
        grad_stats_fn=central_vf_stats_a2c,
        mixins=[
            CentralizedValueMixin
        ])

    MAA2CTorchPolicy = A3CTorchPolicy.with_updates(
        name="MAA2CTorchPolicy",
        get_default_config=lambda: MAA2C_CONFIG,
        postprocess_fn=centralized_critic_postprocessing,
        loss_fn=loss_with_central_critic_a2c,
        mixins=[
            CentralizedValueMixin
        ])

    def get_policy_class(config_):
        if config_["framework"] == "torch":
            return MAA2CTorchPolicy

    MAA2CTrainer = A2CTrainer.with_updates(
        name="MAA2CTrainer",
        default_policy=MAA2CTFPolicy,
        get_policy_class=get_policy_class,
    )

    results = tune.run(MAA2CTrainer, name=args.run + "_" + args.neural_arch + "_" + args.map, stop=stop,
                       config=config, verbose=1, progress_reporter=reporter)

    return results
