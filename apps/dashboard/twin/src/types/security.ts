export interface SecurityDevice {
  id: string
  name: string
  kind: 'Server' | 'Sensor' | 'Rover' | 'Access point'
  zone: string
  status: 'Healthy' | 'Investigate' | 'Unknown'
  address: string
  provenance: 'SYNTHETIC'
}
