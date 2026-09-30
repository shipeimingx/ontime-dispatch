export function fixture(partial = true) {
  return {
    rule_profile_id: 'demo-v1',
    tasks: [
      { id: 'T01', station: 'A', load_kg: 1, window_start_s: 60, window_end_s: 300, service_s: 60, eligible_types: ['UAV', 'AGV'] },
      { id: 'T02', station: 'B', load_kg: 10, window_start_s: 180, window_end_s: 420, service_s: 120, eligible_types: ['UAV', 'AGV'] },
      { id: 'T03', station: 'C', load_kg: 8, window_start_s: 600, window_end_s: 1200, service_s: 120, eligible_types: ['UAV', 'AGV'] },
      ...(partial ? [{ id: 'T04', station: 'D', load_kg: 25, window_start_s: 0, window_end_s: 1800, service_s: 120, eligible_types: ['UAV', 'AGV'] }] : [])
    ],
    vehicles: [
      { id: 'UAV-01', type: 'UAV', available: true, capacity_kg: 2, speed_m_s: 5, trip_limit_s: 600, shift_end_s: 2700, turnaround_s: 120 },
      { id: 'AGV-01', type: 'AGV', available: true, capacity_kg: 20, speed_m_s: 1, trip_limit_s: 1800, shift_end_s: 2700, turnaround_s: 120 }
    ],
    // Type-specific, symmetric depot-to-station distances. Not a geographic road network.
    distances_m: { UAV: { A: 600, B: 240, C: 360, D: 300 }, AGV: { A: 360, B: 240, C: 360, D: 300 } }
  };
}
