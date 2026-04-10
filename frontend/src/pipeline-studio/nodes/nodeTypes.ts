/** React Flow nodeTypes registry — maps all node type_ids to BaseNode */

import BaseNode from './BaseNode'

// All node types use the same BaseNode component,
// which renders dynamically based on the node's data.nodeDef
const nodeTypes: Record<string, typeof BaseNode> = {
  speech_source: BaseNode,
  noise_generator: BaseNode,
  audio_file: BaseNode,
  text_source: BaseNode,
  mixer: BaseNode,
  echo_simulator: BaseNode,
  eq_filter: BaseNode,
  gain: BaseNode,
  audio_buffer: BaseNode,
  network_sim: BaseNode,
  telephony_codec: BaseNode,
  aec: BaseNode,
  aec_residual: BaseNode,
  agc: BaseNode,
  noise_reduction: BaseNode,
  sample_rate_converter: BaseNode,
  time_delay: BaseNode,
  doubletalk_metrics: BaseNode,
  far_end_source: BaseNode,
  telephony_judge: BaseNode,
  tts: BaseNode,
  stt: BaseNode,
  llm: BaseNode,
  llm_realtime: BaseNode,
  eval_analysis: BaseNode,
  safety_critical_eval: BaseNode,
  compliance_eval: BaseNode,
  trust_brand_eval: BaseNode,
  ux_quality_eval: BaseNode,
  router: BaseNode,
  histogram: BaseNode,
  text_output: BaseNode,
  audio_output: BaseNode,
  eval_output: BaseNode,
}

export default nodeTypes
