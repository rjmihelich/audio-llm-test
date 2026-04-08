/** React Flow nodeTypes registry — maps all node type_ids to BaseNode */

import BaseNode from './BaseNode'

// All node types use the same BaseNode component,
// which renders dynamically based on the node's data.nodeDef
const nodeTypes: Record<string, typeof BaseNode> = {
  speech_source: BaseNode,
  noise_generator: BaseNode,
  audio_file: BaseNode,
  mixer: BaseNode,
  echo_simulator: BaseNode,
  eq_filter: BaseNode,
  gain: BaseNode,
  audio_preprocess: BaseNode,
  audio_postprocess: BaseNode,
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
  tts: BaseNode,
  stt: BaseNode,
  llm: BaseNode,
  llm_realtime: BaseNode,
  eval_analysis: BaseNode,
  text_output: BaseNode,
  audio_output: BaseNode,
  eval_output: BaseNode,
}

export default nodeTypes
