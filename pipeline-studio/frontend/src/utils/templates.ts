/** Client-side template definitions matching the 5 whiteboard diagrams.
 *  Used as fallback when backend is unavailable. */

interface TemplateNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: {
    type_id: string
    label: string
    config: Record<string, unknown>
  }
}

interface TemplateEdge {
  id: string
  source: string
  sourceHandle: string
  target: string
  targetHandle: string
  data: { edge_type: string }
}

export interface Template {
  id: string
  name: string
  description: string
  graph_json: {
    nodes: TemplateNode[]
    edges: TemplateEdge[]
    viewport: { x: number; y: number; zoom: number }
  }
}

function n(id: string, type: string, x: number, y: number, label: string, config: Record<string, unknown> = {}): TemplateNode {
  return { id, type, position: { x, y }, data: { type_id: type, label, config } }
}

function e(id: string, src: string, srcH: string, tgt: string, tgtH: string, edgeType = 'normal'): TemplateEdge {
  return { id, source: src, sourceHandle: srcH, target: tgt, targetHandle: tgtH, data: { edge_type: edgeType } }
}

// Template 1: Direct Realtime
const t1_nodes: TemplateNode[] = [
  n('t1_speech', 'speech_source', 0, 100, 'Speech'),
  n('t1_babble', 'noise_generator', 0, 250, 'Babble Noise', { noise_type: 'babble' }),
  n('t1_road', 'noise_generator', 0, 400, 'Road Noise', { noise_type: 'traffic' }),
  n('t1_wind', 'noise_generator', 0, 550, 'Wind Noise', { noise_type: 'wind' }),
  n('t1_mixer', 'mixer', 300, 300, 'Audio Mixer', { snr_db: 15, mixing_mode: 'snr' }),
  n('t1_llm', 'llm_realtime', 600, 300, 'GPT Realtime', { model: 'gpt-4o-realtime-preview', voice: 'alloy', system_prompt: 'You are a helpful in-car voice assistant.' }),
  n('t1_eval', 'eval_analysis', 900, 300, 'Evaluation & Analysis', { evaluators: 'all', enable_latency_tracking: true }),
  n('t1_out', 'eval_output', 1200, 300, 'Results'),
]
const t1_edges: TemplateEdge[] = [
  e('t1_e1', 't1_speech', 'audio_out', 't1_mixer', 'audio_in_0'),
  e('t1_e2', 't1_babble', 'audio_out', 't1_mixer', 'audio_in_1'),
  e('t1_e3', 't1_road', 'audio_out', 't1_mixer', 'audio_in_2'),
  e('t1_e4', 't1_wind', 'audio_out', 't1_mixer', 'audio_in_3'),
  e('t1_e5', 't1_mixer', 'audio_out', 't1_llm', 'audio_in'),
  e('t1_e6', 't1_llm', 'text_out', 't1_eval', 'text_in'),
  e('t1_e7', 't1_llm', 'audio_out', 't1_eval', 'audio_in'),
  e('t1_e8', 't1_eval', 'eval_out', 't1_out', 'eval_in'),
]

// Template 2: Network Simulation
const t2_nodes: TemplateNode[] = [
  n('t2_speech', 'speech_source', 0, 100, 'Speech'),
  n('t2_noise', 'noise_generator', 0, 300, 'Noise', { noise_type: 'pink_lpf' }),
  n('t2_mixer', 'mixer', 250, 200, 'Audio Mixer', { snr_db: 20 }),
  n('t2_buf', 'audio_buffer', 500, 200, 'Audio Buffering', { chunk_ms: 20 }),
  n('t2_net_in', 'network_sim', 700, 200, 'Network Sim (Ingress)', { latency_ms: 80, jitter_ms: 15, packet_loss_pct: 1 }),
  n('t2_llm', 'llm', 950, 200, 'LLM', { backend: 'openai:gpt-4o-audio-preview' }),
  n('t2_net_out', 'network_sim', 1200, 200, 'Network Sim (Egress)', { latency_ms: 50, jitter_ms: 10 }),
  n('t2_eval', 'eval_analysis', 1450, 200, 'Evaluation & Analysis', { evaluators: 'all' }),
  n('t2_out', 'eval_output', 1700, 200, 'Results'),
]
const t2_edges: TemplateEdge[] = [
  e('t2_e1', 't2_speech', 'audio_out', 't2_mixer', 'audio_in_0'),
  e('t2_e2', 't2_noise', 'audio_out', 't2_mixer', 'audio_in_1'),
  e('t2_e3', 't2_mixer', 'audio_out', 't2_buf', 'audio_in'),
  e('t2_e4', 't2_buf', 'audio_out', 't2_net_in', 'audio_in'),
  e('t2_e5', 't2_net_in', 'audio_out', 't2_llm', 'audio_in'),
  e('t2_e6', 't2_llm', 'text_out', 't2_net_out', 'text_in'),
  e('t2_e7', 't2_net_out', 'text_out', 't2_eval', 'text_in'),
  e('t2_e8', 't2_eval', 'eval_out', 't2_out', 'eval_in'),
]

// Template 3: Echo + Network
const t3_nodes: TemplateNode[] = [
  n('t3_speech', 'speech_source', 0, 100, 'Speech'),
  n('t3_noise', 'noise_generator', 0, 300, 'Babble Noise', { noise_type: 'babble' }),
  n('t3_mixer', 'mixer', 250, 200, 'Audio Mixer', { snr_db: 15 }),
  n('t3_echo', 'echo_simulator', 500, 200, 'Echo Simulator', { delay_ms: 120, gain_db: -10 }),
  n('t3_net_in', 'network_sim', 750, 200, 'Network Sim (Ingress)', { latency_ms: 80, jitter_ms: 15 }),
  n('t3_llm', 'llm', 1000, 200, 'LLM', { backend: 'openai:gpt-4o-audio-preview' }),
  n('t3_net_out', 'network_sim', 1250, 200, 'Network Sim (Egress)', { latency_ms: 50, jitter_ms: 10 }),
  n('t3_eval', 'eval_analysis', 1500, 200, 'Evaluation & Analysis', { evaluators: 'all' }),
  n('t3_out', 'eval_output', 1750, 200, 'Results'),
]
const t3_edges: TemplateEdge[] = [
  e('t3_e1', 't3_speech', 'audio_out', 't3_mixer', 'audio_in_0'),
  e('t3_e2', 't3_noise', 'audio_out', 't3_mixer', 'audio_in_1'),
  e('t3_e3', 't3_mixer', 'audio_out', 't3_echo', 'mic_in'),
  e('t3_e4', 't3_echo', 'audio_out', 't3_net_in', 'audio_in'),
  e('t3_e5', 't3_net_in', 'audio_out', 't3_llm', 'audio_in'),
  e('t3_e6', 't3_llm', 'text_out', 't3_net_out', 'text_in'),
  e('t3_e7', 't3_net_out', 'text_out', 't3_eval', 'text_in'),
  e('t3_e8', 't3_net_out', 'audio_out', 't3_echo', 'speaker_in', 'feedback'),
  e('t3_e9', 't3_eval', 'eval_out', 't3_out', 'eval_in'),
]

// Template 4: Full Audio Processing
const t4_nodes: TemplateNode[] = [
  n('t4_speech', 'speech_source', 0, 100, 'Speech'),
  n('t4_noise', 'noise_generator', 0, 300, 'Babble Noise', { noise_type: 'babble' }),
  n('t4_road', 'noise_generator', 0, 450, 'Road Noise', { noise_type: 'traffic' }),
  n('t4_mixer', 'mixer', 250, 200, 'Audio Mixer', { snr_db: 15 }),
  n('t4_echo', 'echo_simulator', 450, 200, 'Echo Simulator', { delay_ms: 100, gain_db: -8 }),
  n('t4_net_in', 'network_sim', 650, 200, 'Network Sim (In)', { latency_ms: 60, jitter_ms: 10 }),
  n('t4_preproc', 'audio_preprocess', 850, 200, 'Audio Pre-Processing', { enable_agc: true, agc_target_db: -3, enable_noise_gate: true, noise_gate_threshold_db: -40 }),
  n('t4_llm', 'llm', 1050, 200, 'LLM', { backend: 'openai:gpt-4o-audio-preview' }),
  n('t4_postproc', 'audio_postprocess', 1250, 200, 'Audio Post-Processing', { normalize: true, enable_limiter: true }),
  n('t4_net_out', 'network_sim', 1450, 200, 'Network Sim (Out)', { latency_ms: 50, jitter_ms: 10 }),
  n('t4_eval', 'eval_analysis', 1650, 200, 'Evaluation & Analysis', { evaluators: 'all' }),
  n('t4_out', 'eval_output', 1900, 200, 'Results'),
]
const t4_edges: TemplateEdge[] = [
  e('t4_e1', 't4_speech', 'audio_out', 't4_mixer', 'audio_in_0'),
  e('t4_e2', 't4_noise', 'audio_out', 't4_mixer', 'audio_in_1'),
  e('t4_e3', 't4_road', 'audio_out', 't4_mixer', 'audio_in_2'),
  e('t4_e4', 't4_mixer', 'audio_out', 't4_echo', 'mic_in'),
  e('t4_e5', 't4_echo', 'audio_out', 't4_net_in', 'audio_in'),
  e('t4_e6', 't4_net_in', 'audio_out', 't4_preproc', 'audio_in'),
  e('t4_e7', 't4_preproc', 'audio_out', 't4_llm', 'audio_in'),
  e('t4_e8', 't4_llm', 'text_out', 't4_eval', 'text_in'),
  e('t4_e9', 't4_llm', 'audio_out', 't4_postproc', 'audio_in'),
  e('t4_e10', 't4_postproc', 'audio_out', 't4_net_out', 'audio_in'),
  e('t4_e11', 't4_net_out', 'audio_out', 't4_echo', 'speaker_in', 'feedback'),
  e('t4_e12', 't4_eval', 'eval_out', 't4_out', 'eval_in'),
]

// Template 5: Full STT/LLM/TTS Loop
const t5_nodes: TemplateNode[] = [
  n('t5_speech', 'speech_source', 0, 100, 'Speech'),
  n('t5_noise', 'noise_generator', 0, 300, 'Babble Noise', { noise_type: 'babble' }),
  n('t5_road', 'noise_generator', 0, 450, 'Road Noise', { noise_type: 'traffic' }),
  n('t5_mixer', 'mixer', 200, 200, 'Audio Mixer', { snr_db: 15 }),
  n('t5_echo', 'echo_simulator', 380, 200, 'Echo Simulator', { delay_ms: 100, gain_db: -8 }),
  n('t5_preproc', 'audio_preprocess', 560, 200, 'Audio Pre-Processing', { enable_agc: true }),
  n('t5_stt', 'stt', 740, 200, 'STT', { backend: 'whisper_local', model_size: 'base' }),
  n('t5_net_in', 'network_sim', 920, 200, 'Network Sim (In)', { latency_ms: 60, jitter_ms: 10 }),
  n('t5_llm', 'llm', 1100, 200, 'LLM', { backend: 'anthropic:claude-haiku-4-5-20251001' }),
  n('t5_net_out', 'network_sim', 1280, 200, 'Network Sim (Out)', { latency_ms: 50, jitter_ms: 10 }),
  n('t5_tts', 'tts', 1460, 200, 'TTS', { provider: 'edge', voice_id: '' }),
  n('t5_postproc', 'audio_postprocess', 1640, 200, 'Audio Post-Processing', { normalize: true }),
  n('t5_eval', 'eval_analysis', 1820, 200, 'Evaluation & Analysis', { evaluators: 'all' }),
  n('t5_out', 'eval_output', 2050, 200, 'Results'),
]
const t5_edges: TemplateEdge[] = [
  e('t5_e1', 't5_speech', 'audio_out', 't5_mixer', 'audio_in_0'),
  e('t5_e2', 't5_noise', 'audio_out', 't5_mixer', 'audio_in_1'),
  e('t5_e3', 't5_road', 'audio_out', 't5_mixer', 'audio_in_2'),
  e('t5_e4', 't5_mixer', 'audio_out', 't5_echo', 'mic_in'),
  e('t5_e5', 't5_echo', 'audio_out', 't5_preproc', 'audio_in'),
  e('t5_e6', 't5_preproc', 'audio_out', 't5_stt', 'audio_in'),
  e('t5_e7', 't5_stt', 'text_out', 't5_net_in', 'text_in'),
  e('t5_e8', 't5_net_in', 'text_out', 't5_llm', 'text_in'),
  e('t5_e9', 't5_llm', 'text_out', 't5_net_out', 'text_in'),
  e('t5_e10', 't5_net_out', 'text_out', 't5_tts', 'text_in'),
  e('t5_e11', 't5_tts', 'audio_out', 't5_postproc', 'audio_in'),
  e('t5_e12', 't5_postproc', 'audio_out', 't5_echo', 'speaker_in', 'feedback'),
  e('t5_e13', 't5_llm', 'text_out', 't5_eval', 'text_in'),
  e('t5_e14', 't5_eval', 'eval_out', 't5_out', 'eval_in'),
]

export const STATIC_TEMPLATES: Template[] = [
  {
    id: 'tmpl_direct_realtime',
    name: 'Direct Realtime',
    description: 'Speech + noise → GPT Realtime → Evaluation. Simplest pipeline for testing multimodal LLMs with noise.',
    graph_json: { nodes: t1_nodes, edges: t1_edges, viewport: { x: 0, y: 0, zoom: 0.8 } },
  },
  {
    id: 'tmpl_network_sim',
    name: 'Network Simulation',
    description: 'Audio through network simulators on both sides of the LLM, modeling real-world latency and packet loss.',
    graph_json: { nodes: t2_nodes, edges: t2_edges, viewport: { x: 0, y: 0, zoom: 0.7 } },
  },
  {
    id: 'tmpl_echo_network',
    name: 'Echo + Network',
    description: 'Acoustic echo coupling path with network simulation. Tests LLM performance with echo feedback.',
    graph_json: { nodes: t3_nodes, edges: t3_edges, viewport: { x: 0, y: 0, zoom: 0.65 } },
  },
  {
    id: 'tmpl_full_audio',
    name: 'Full Audio Processing',
    description: 'Complete audio chain: mixer → echo → network → pre-processing → LLM → post-processing → network → eval.',
    graph_json: { nodes: t4_nodes, edges: t4_edges, viewport: { x: 0, y: 0, zoom: 0.55 } },
  },
  {
    id: 'tmpl_full_stt_tts',
    name: 'Full STT/LLM/TTS Loop',
    description: 'Full voice assistant loop: speech → STT → LLM → TTS with echo coupling, network sim, and pre/post processing.',
    graph_json: { nodes: t5_nodes, edges: t5_edges, viewport: { x: 0, y: 0, zoom: 0.5 } },
  },
]
