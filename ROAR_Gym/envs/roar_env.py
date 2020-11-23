import gym
from ROAR_Sim.configurations.configuration import Configuration as CarlaConfig
import logging
import pygame
from ROAR.configurations.configuration import Configuration as AgentConfig
from ROAR_Sim.carla_client.carla_runner import CarlaRunner
from ROAR.utilities_module.vehicle_models import VehicleControl
from typing import Optional, Tuple, Any, Dict
from ROAR.agent_module.agent import Agent
from ROAR.agent_module.pure_pursuit_agent import PurePursuitAgent
from ROAR.agent_module.pid_agent import PIDAgent
from pprint import pprint

class ROAREnv(gym.Env):
    def __init__(self, params: Dict[str, Any]):
        """
        carla_config: CarlaConfig,
                 agent_config: AgentConfig,
                 npc_agent_class, num_frames_per_step: int = 1,
                 use_manual_control: bool = False
        Args:
            params:
        """
        carla_config: CarlaConfig = params["carla_config"]
        agent_config: AgentConfig = params["agent_config"]
        npc_agent_class = params.get("npc_agent_class", PurePursuitAgent)
        num_frames_per_step: int = params.get("num_frames_per_step", 1)
        use_manual_control: bool = params.get("use_manual_control", False)

        self.logger = logging.getLogger("ROAR Gym")
        self.agent_config = agent_config
        self.npc_agent_class = npc_agent_class
        self.carla_config = carla_config
        self.use_manual_control = use_manual_control
        self.carla_runner = CarlaRunner(carla_settings=self.carla_config,
                                        agent_settings=self.agent_config,
                                        npc_agent_class=self.npc_agent_class)
        try:

            self.num_frames_per_step = num_frames_per_step
            vehicle = self.carla_runner.set_carla_world()
            self.agent = PIDAgent(vehicle=vehicle, agent_settings=self.agent_config)
            self.clock: Optional[pygame.time.Clock] = None
            self._start_game()
        except Exception as e:
            self.logger.error(e)
            self.carla_runner.on_finish()

    def step(self, action: VehicleControl) -> Tuple[Agent, float, bool, dict]:
        self.clock.tick_busy_loop(60)
        should_continue, carla_control = self.carla_runner.controller.parse_events(client=self.carla_runner.client,
                                                                                   world=self.carla_runner.world,
                                                                                   clock=self.clock)

        self.carla_runner.world.tick(self.clock)

        sensor_data, new_vehicle = self.carla_runner.convert_data()

        if self.carla_runner.carla_settings.should_spawn_npcs:
            self.carla_runner.execute_npcs_step()

        if self.carla_runner.agent_settings.enable_autopilot:
            if self.agent is None:
                raise Exception(
                    "In autopilot mode, but no agent is defined.")
            agent_control = self.agent.run_step(vehicle=new_vehicle,
                                                sensors_data=sensor_data)
            if not self.use_manual_control:
                carla_control = self.carla_runner.carla_bridge. \
                    convert_control_from_agent_to_source(agent_control)
        self.carla_runner.world.player.apply_control(carla_control)
        return self._get_obs(), self._get_reward(), self._terminal(), self._get_info()

    def reset(self):
        self.carla_runner.on_finish()
        self.carla_runner = CarlaRunner(agent_settings=self.agent_config,
                                        carla_settings=self.carla_config,
                                        npc_agent_class=self.npc_agent_class)
        vehicle = self.carla_runner.set_carla_world()
        self.agent = PIDAgent(vehicle=vehicle, agent_settings=self.agent_config)
        self.clock: Optional[pygame.time.Clock] = None
        self._start_game()

    def render(self, mode='ego'):
        self.carla_runner.world.render(display=self.carla_runner.display)
        pygame.display.flip()

    def _start_game(self):
        try:
            self.logger.debug("Initiating game")
            self.agent.start_module_threads()
            self.clock = pygame.time.Clock()
            self.start_simulation_time = self.carla_runner.world.hud.simulation_time
            self.start_vehicle_position = self.agent.vehicle.transform.location.to_array()
        except Exception as e:
            self.logger.error(e)

    def _get_reward(self) -> float:
        return -1

    def _terminal(self) -> bool:
        return self.agent.is_done  # TODO temporary, needs to be changed

    def _get_info(self) -> dict:
        pass

    def _get_obs(self) -> Agent:
        return self.agent