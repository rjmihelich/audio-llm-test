/** Static node type registry — fallback when backend is unavailable */

import type { NodeTypeRegistry } from '../api/client'

export const STATIC_REGISTRY: NodeTypeRegistry = {
  categories: {
    sources: { label: 'Audio Sources', color: '#A3E635' },
    processing: { label: 'Audio Processing', color: '#FBBF24' },
    network: { label: 'Network', color: '#F87171' },
    speech: { label: 'Speech', color: '#818CF8' },
    llm: { label: 'LLM', color: '#34D399' },
    evaluation: { label: 'Evaluation', color: '#FB923C' },
    output: { label: 'Output', color: '#94A3B8' },
  },
  node_types: {
    speech_source: {
      type_id: 'speech_source', label: 'Speech Source', category: 'sources', color: '#A3E635',
      description: 'Clean speech audio from corpus or PipelineInput',
      dynamic_inputs: false,
      inputs: [],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'source_mode', type: 'select', label: 'Source', default: 'pipeline_input', options: [{ value: 'pipeline_input', label: 'From Test Case' }, { value: 'file', label: 'Audio File' }], description: '' },
      ],
    },
    noise_generator: {
      type_id: 'noise_generator', label: 'Noise Generator', category: 'sources', color: '#A3E635',
      description: 'Generate noise: white, pink, babble, traffic, wind',
      dynamic_inputs: false,
      inputs: [],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'noise_type', type: 'select', label: 'Noise Type', default: 'pink_lpf', options: [{ value: 'white', label: 'White' }, { value: 'pink', label: 'Pink' }, { value: 'pink_lpf', label: 'Pink (LPF)' }, { value: 'babble', label: 'Babble' }, { value: 'traffic', label: 'Traffic' }, { value: 'wind', label: 'Wind' }], description: '' },
        { name: 'seed', type: 'number', label: 'Random Seed', default: null, description: 'Leave empty for random' },
      ],
    },
    audio_file: {
      type_id: 'audio_file', label: 'Audio File', category: 'sources', color: '#A3E635',
      description: 'Load audio from a WAV file',
      dynamic_inputs: false,
      inputs: [],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'file_path', type: 'string', label: 'File Path', default: '', description: '' },
      ],
    },
    mixer: {
      type_id: 'mixer', label: 'Audio Mixer', category: 'processing', color: '#FBBF24',
      description: 'Mix N audio inputs at specified SNR levels',
      dynamic_inputs: true,
      inputs: [
        { name: 'audio_in_0', type: 'audio', required: true, description: 'Primary (speech)' },
        { name: 'audio_in_1', type: 'audio', required: false, description: 'Noise 1' },
      ],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'snr_db', type: 'slider', label: 'SNR (dB)', default: 20, min: -10, max: 40, step: 1, description: '' },
        { name: 'mixing_mode', type: 'select', label: 'Mode', default: 'snr', options: [{ value: 'snr', label: 'SNR-calibrated' }, { value: 'equal', label: 'Equal gain' }], description: '' },
      ],
    },
    echo_simulator: {
      type_id: 'echo_simulator', label: 'Echo Simulator', category: 'processing', color: '#FBBF24',
      description: 'Simulate acoustic echo coupling path',
      dynamic_inputs: false,
      inputs: [
        { name: 'mic_in', type: 'audio', required: true, description: 'Mic input' },
        { name: 'speaker_in', type: 'audio', required: false, description: 'Speaker feedback' },
      ],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'delay_ms', type: 'slider', label: 'Delay (ms)', default: 100, min: 0, max: 500, step: 10, description: '' },
        { name: 'gain_db', type: 'slider', label: 'Gain (dB)', default: -6, min: -60, max: 0, step: 1, description: '' },
      ],
    },
    eq_filter: {
      type_id: 'eq_filter', label: 'EQ Filter', category: 'processing', color: '#FBBF24',
      description: 'Biquad filter chain',
      dynamic_inputs: false,
      inputs: [{ name: 'audio_in', type: 'audio', required: true, description: '' }],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'filters', type: 'json', label: 'Filter Chain', default: [], description: '[{"type":"lpf","freq":8000,"q":0.707}]' },
      ],
    },
    gain: {
      type_id: 'gain', label: 'Gain', category: 'processing', color: '#FBBF24',
      description: 'Simple volume adjustment',
      dynamic_inputs: false,
      inputs: [{ name: 'audio_in', type: 'audio', required: true, description: '' }],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'gain_db', type: 'slider', label: 'Gain (dB)', default: 0, min: -60, max: 24, step: 0.5, description: '' },
      ],
    },
    audio_preprocess: {
      type_id: 'audio_preprocess', label: 'Audio Pre-Processing', category: 'processing', color: '#FBBF24',
      description: 'AEC, AGC, noise gate, VAD',
      dynamic_inputs: false,
      inputs: [{ name: 'audio_in', type: 'audio', required: true, description: '' }],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'enable_agc', type: 'boolean', label: 'Auto Gain Control', default: true, description: '' },
        { name: 'enable_noise_gate', type: 'boolean', label: 'Noise Gate', default: false, description: '' },
      ],
    },
    audio_postprocess: {
      type_id: 'audio_postprocess', label: 'Audio Post-Processing', category: 'processing', color: '#FBBF24',
      description: 'Normalization, limiting',
      dynamic_inputs: false,
      inputs: [{ name: 'audio_in', type: 'audio', required: true, description: '' }],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'normalize', type: 'boolean', label: 'Normalize', default: true, description: '' },
        { name: 'enable_limiter', type: 'boolean', label: 'Limiter', default: true, description: '' },
      ],
    },
    audio_buffer: {
      type_id: 'audio_buffer', label: 'Audio Buffer', category: 'processing', color: '#FBBF24',
      description: 'Chunk/buffer audio for streaming simulation',
      dynamic_inputs: false,
      inputs: [{ name: 'audio_in', type: 'audio', required: true, description: '' }],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'chunk_ms', type: 'slider', label: 'Chunk Size (ms)', default: 20, min: 5, max: 200, step: 5, description: '' },
      ],
    },
    network_sim: {
      type_id: 'network_sim', label: 'Network Simulator', category: 'network', color: '#F87171',
      description: 'Simulate network latency, jitter, packet loss',
      dynamic_inputs: false,
      inputs: [
        { name: 'audio_in', type: 'audio', required: false, description: '' },
        { name: 'text_in', type: 'text', required: false, description: '' },
      ],
      outputs: [
        { name: 'audio_out', type: 'audio', required: false, description: '' },
        { name: 'text_out', type: 'text', required: false, description: '' },
      ],
      config_fields: [
        { name: 'latency_ms', type: 'slider', label: 'Latency (ms)', default: 50, min: 0, max: 2000, step: 10, description: '' },
        { name: 'jitter_ms', type: 'slider', label: 'Jitter (ms)', default: 10, min: 0, max: 500, step: 5, description: '' },
        { name: 'packet_loss_pct', type: 'slider', label: 'Packet Loss (%)', default: 0, min: 0, max: 50, step: 0.5, description: '' },
      ],
    },
    tts: {
      type_id: 'tts', label: 'Text-to-Speech', category: 'speech', color: '#818CF8',
      description: 'Convert text to audio',
      dynamic_inputs: false,
      inputs: [{ name: 'text_in', type: 'text', required: true, description: '' }],
      outputs: [{ name: 'audio_out', type: 'audio', required: false, description: '' }],
      config_fields: [
        { name: 'provider', type: 'select', label: 'Provider', default: 'edge', options: [{ value: 'openai', label: 'OpenAI' }, { value: 'elevenlabs', label: 'ElevenLabs' }, { value: 'edge', label: 'Edge (Free)' }, { value: 'piper', label: 'Piper (Local)' }], description: '' },
        { name: 'voice_id', type: 'string', label: 'Voice ID', default: '', description: '' },
      ],
    },
    stt: {
      type_id: 'stt', label: 'Speech-to-Text', category: 'speech', color: '#818CF8',
      description: 'Transcribe audio to text',
      dynamic_inputs: false,
      inputs: [{ name: 'audio_in', type: 'audio', required: true, description: '' }],
      outputs: [{ name: 'text_out', type: 'text', required: false, description: '' }],
      config_fields: [
        { name: 'backend', type: 'select', label: 'Backend', default: 'whisper_local', options: [{ value: 'whisper_local', label: 'Whisper (Local)' }, { value: 'whisper_api', label: 'Whisper (API)' }, { value: 'deepgram', label: 'Deepgram' }], description: '' },
      ],
    },
    llm: {
      type_id: 'llm', label: 'LLM', category: 'llm', color: '#34D399',
      description: 'Request/response LLM (GPT-4o, Gemini, Claude, Ollama)',
      dynamic_inputs: false,
      inputs: [
        { name: 'audio_in', type: 'audio', required: false, description: 'Audio input' },
        { name: 'text_in', type: 'text', required: false, description: 'Text input' },
      ],
      outputs: [
        { name: 'text_out', type: 'text', required: false, description: '' },
        { name: 'audio_out', type: 'audio', required: false, description: '' },
      ],
      config_fields: [
        { name: 'backend', type: 'select', label: 'Backend', default: 'openai:gpt-4o-audio-preview', options: [{ value: 'openai:gpt-4o-audio-preview', label: 'GPT-4o Audio' }, { value: 'gemini:gemini-2.0-flash', label: 'Gemini 2.0 Flash' }, { value: 'anthropic:claude-haiku-4-5-20251001', label: 'Claude Haiku' }, { value: 'ollama:mistral', label: 'Ollama Mistral' }], description: '' },
        { name: 'system_prompt', type: 'string', label: 'System Prompt', default: 'You are a helpful in-car voice assistant.', description: '' },
        { name: 'temperature', type: 'slider', label: 'Temperature', default: 0.7, min: 0, max: 2, step: 0.1, description: '' },
      ],
    },
    llm_realtime: {
      type_id: 'llm_realtime', label: 'LLM Realtime', category: 'llm', color: '#34D399',
      description: 'Streaming WebSocket LLM (OpenAI Realtime API)',
      dynamic_inputs: false,
      inputs: [{ name: 'audio_in', type: 'audio', required: true, description: 'Streaming audio' }],
      outputs: [
        { name: 'text_out', type: 'text', required: false, description: '' },
        { name: 'audio_out', type: 'audio', required: false, description: '' },
      ],
      config_fields: [
        { name: 'model', type: 'select', label: 'Model', default: 'gpt-4o-realtime-preview', options: [{ value: 'gpt-4o-realtime-preview', label: 'GPT-4o Realtime' }, { value: 'gpt-4o-mini-realtime-preview', label: 'GPT-4o Mini Realtime' }], description: '' },
        { name: 'voice', type: 'select', label: 'Voice', default: 'alloy', options: [{ value: 'alloy', label: 'Alloy' }, { value: 'echo', label: 'Echo' }, { value: 'shimmer', label: 'Shimmer' }, { value: 'ash', label: 'Ash' }, { value: 'coral', label: 'Coral' }, { value: 'sage', label: 'Sage' }], description: '' },
        { name: 'turn_detection', type: 'select', label: 'Turn Detection', default: 'server_vad', options: [{ value: 'server_vad', label: 'Server VAD' }, { value: 'manual', label: 'Manual' }], description: '' },
        { name: 'temperature', type: 'slider', label: 'Temperature', default: 0.8, min: 0, max: 2, step: 0.1, description: '' },
        { name: 'system_prompt', type: 'string', label: 'Instructions', default: 'You are a helpful in-car voice assistant.', description: '' },
      ],
    },
    eval_analysis: {
      type_id: 'eval_analysis', label: 'Evaluation & Analysis', category: 'evaluation', color: '#FB923C',
      description: 'Combined evaluation engine',
      dynamic_inputs: false,
      inputs: [
        { name: 'text_in', type: 'text', required: true, description: 'LLM response text' },
        { name: 'audio_in', type: 'audio', required: false, description: 'LLM response audio' },
      ],
      outputs: [{ name: 'eval_out', type: 'evaluation', required: false, description: '' }],
      config_fields: [
        { name: 'evaluators', type: 'select', label: 'Evaluators', default: 'command_match', options: [{ value: 'command_match', label: 'Command Match' }, { value: 'llm_judge', label: 'LLM Judge' }, { value: 'wer', label: 'WER' }, { value: 'all', label: 'All' }], description: '' },
        { name: 'pass_threshold', type: 'slider', label: 'Pass Threshold', default: 0.6, min: 0, max: 1, step: 0.05, description: '' },
      ],
    },
    text_output: {
      type_id: 'text_output', label: 'Text Output', category: 'output', color: '#94A3B8',
      description: 'Display text result',
      dynamic_inputs: false,
      inputs: [{ name: 'text_in', type: 'text', required: true, description: '' }],
      outputs: [],
      config_fields: [{ name: 'label', type: 'string', label: 'Label', default: 'Output', description: '' }],
    },
    audio_output: {
      type_id: 'audio_output', label: 'Audio Output', category: 'output', color: '#94A3B8',
      description: 'Save or play audio result',
      dynamic_inputs: false,
      inputs: [{ name: 'audio_in', type: 'audio', required: true, description: '' }],
      outputs: [],
      config_fields: [{ name: 'label', type: 'string', label: 'Label', default: 'Output', description: '' }],
    },
    eval_output: {
      type_id: 'eval_output', label: 'Eval Output', category: 'output', color: '#94A3B8',
      description: 'Display evaluation results',
      dynamic_inputs: false,
      inputs: [{ name: 'eval_in', type: 'evaluation', required: true, description: '' }],
      outputs: [],
      config_fields: [{ name: 'label', type: 'string', label: 'Label', default: 'Results', description: '' }],
    },
  },
}
