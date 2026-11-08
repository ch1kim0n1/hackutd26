import type { Device, Observation, Point } from './model'
import type { NemotronTransport } from './agents'

export interface SourceEnvelope<T> { source: 'mock' | 'ros2' | 'kismet' | 'nemotron'; provenance: 'DEMO' | 'REPLAY' | 'LIVE'; sequence: number; timestamp: string; payload: T }
export interface RoverPoseMessage { robotId: string; position: Point; heading: number; battery: number; emergencyStop: boolean }
export interface ROS2ReadAdapter { subscribePose(listener: (message: SourceEnvelope<RoverPoseMessage>) => void): () => void }
export interface KismetReadAdapter { subscribeObservation(listener: (message: SourceEnvelope<Observation>) => void): () => void; listDevices(signal?: AbortSignal): Promise<SourceEnvelope<Device[]>> }
export interface AuthorizedMissionRequest { requestId: string; robotId: string; target: Point; operatorIdentity: string; authorizationToken: string; policyDecisionId: string }
/** Future backend boundary: implementations MUST validate identity, policy, geofence and E-stop server-side. */
export interface RoboticsCommandGateway { requestMission(request: AuthorizedMissionRequest, signal?: AbortSignal): Promise<{ accepted: boolean; missionId?: string; reason: string }> }
export interface CommandAdapters { ros2?: ROS2ReadAdapter; kismet?: KismetReadAdapter; nemotron?: NemotronTransport; commands?: RoboticsCommandGateway }
/** No URLs, API keys, network requests or hardware commands are installed by the demo. */
export const DEMO_ADAPTERS: Readonly<CommandAdapters> = Object.freeze({})
