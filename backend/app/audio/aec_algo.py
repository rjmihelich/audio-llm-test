"""Adaptive acoustic echo cancellation algorithms.

Implements NLMS, RLS, and Kalman filter-based AEC.
All operate sample-by-sample on AudioBuffer objects.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import AudioBuffer


@dataclass(frozen=True)
class AECResult:
    """Result of adaptive echo cancellation."""
    output: AudioBuffer        # echo-cancelled signal
    echo_estimate: AudioBuffer  # estimated echo component


def aec_nlms(
    mic: AudioBuffer,
    ref: AudioBuffer,
    *,
    filter_length_ms: float = 200,
    step_size: float = 0.1,
    regularization: float = 1e-6,
) -> AECResult:
    """Normalized Least Mean Squares adaptive echo canceller.

    Args:
        mic: Microphone signal (near-end + echo).
        ref: Far-end reference signal (played through speaker).
        filter_length_ms: Adaptive filter length in milliseconds.
        step_size: NLMS step size (mu). Range [0.01, 1.0].
        regularization: Diagonal loading to prevent division by zero.
    """
    sr = mic.sample_rate
    n_taps = max(1, int(filter_length_ms * sr / 1000))

    # Align lengths
    length = min(len(mic.samples), len(ref.samples))
    d = mic.samples[:length].astype(np.float64)
    x = ref.samples[:length].astype(np.float64)

    w = np.zeros(n_taps, dtype=np.float64)
    output = np.zeros(length, dtype=np.float64)
    echo_est = np.zeros(length, dtype=np.float64)

    # Buffered reference for convolution
    x_buf = np.zeros(n_taps, dtype=np.float64)

    for n in range(length):
        # Shift new sample into reference buffer
        x_buf[1:] = x_buf[:-1]
        x_buf[0] = x[n]

        # Filter output (estimated echo)
        y_hat = np.dot(w, x_buf)
        echo_est[n] = y_hat

        # Error signal (echo-cancelled)
        e = d[n] - y_hat
        output[n] = e

        # NLMS weight update
        norm = np.dot(x_buf, x_buf) + regularization
        w += (step_size / norm) * e * x_buf

    return AECResult(
        output=AudioBuffer(samples=output.astype(np.float32), sample_rate=sr),
        echo_estimate=AudioBuffer(samples=echo_est.astype(np.float32), sample_rate=sr),
    )


def aec_rls(
    mic: AudioBuffer,
    ref: AudioBuffer,
    *,
    filter_length_ms: float = 200,
    forgetting_factor: float = 0.999,
    regularization: float = 1e-6,
) -> AECResult:
    """Recursive Least Squares adaptive echo canceller.

    Faster convergence than NLMS but higher computational cost (O(N^2) per sample).

    Args:
        mic: Microphone signal (near-end + echo).
        ref: Far-end reference signal.
        filter_length_ms: Adaptive filter length in milliseconds.
        forgetting_factor: RLS lambda. Closer to 1 = longer memory.
        regularization: Initial inverse correlation matrix scaling.
    """
    sr = mic.sample_rate
    n_taps = max(1, int(filter_length_ms * sr / 1000))

    length = min(len(mic.samples), len(ref.samples))
    d = mic.samples[:length].astype(np.float64)
    x = ref.samples[:length].astype(np.float64)

    w = np.zeros(n_taps, dtype=np.float64)
    P = np.eye(n_taps, dtype=np.float64) / regularization
    output = np.zeros(length, dtype=np.float64)
    echo_est = np.zeros(length, dtype=np.float64)
    x_buf = np.zeros(n_taps, dtype=np.float64)

    lam_inv = 1.0 / forgetting_factor

    for n in range(length):
        x_buf[1:] = x_buf[:-1]
        x_buf[0] = x[n]

        # A priori echo estimate
        y_hat = np.dot(w, x_buf)
        echo_est[n] = y_hat

        # A priori error
        e = d[n] - y_hat
        output[n] = e

        # Kalman gain vector
        Px = P @ x_buf
        denom = forgetting_factor + np.dot(x_buf, Px)
        k = Px / denom

        # Update weights
        w += k * e

        # Update inverse correlation matrix
        P = lam_inv * (P - np.outer(k, Px))

    return AECResult(
        output=AudioBuffer(samples=output.astype(np.float32), sample_rate=sr),
        echo_estimate=AudioBuffer(samples=echo_est.astype(np.float32), sample_rate=sr),
    )


def aec_kalman(
    mic: AudioBuffer,
    ref: AudioBuffer,
    *,
    filter_length_ms: float = 200,
    process_noise: float = 1e-4,
    measurement_noise: float = 0.01,
    regularization: float = 1e-6,
) -> AECResult:
    """Kalman filter-based adaptive echo canceller.

    Models the adaptive filter weights as a state vector that evolves
    over time.  Optimal for non-stationary echo paths (e.g. moving
    occupants, window position changes).

    State model:
        w[n] = w[n-1] + q[n]     (process noise q ~ N(0, Q))
        d[n] = x[n]^T w[n] + r[n] (measurement noise r ~ N(0, R))

    Args:
        mic: Microphone signal (near-end + echo).
        ref: Far-end reference signal.
        filter_length_ms: Adaptive filter length in milliseconds.
        process_noise: Process noise variance Q (controls adaptivity).
        measurement_noise: Measurement noise variance R.
        regularization: Initial state covariance scaling.
    """
    sr = mic.sample_rate
    n_taps = max(1, int(filter_length_ms * sr / 1000))

    length = min(len(mic.samples), len(ref.samples))
    d = mic.samples[:length].astype(np.float64)
    x = ref.samples[:length].astype(np.float64)

    # State (filter weights) and covariance
    w = np.zeros(n_taps, dtype=np.float64)
    P = np.eye(n_taps, dtype=np.float64) * regularization

    Q = process_noise  # scalar, applied as Q * I
    R = measurement_noise

    output = np.zeros(length, dtype=np.float64)
    echo_est = np.zeros(length, dtype=np.float64)
    x_buf = np.zeros(n_taps, dtype=np.float64)

    for n in range(length):
        x_buf[1:] = x_buf[:-1]
        x_buf[0] = x[n]

        # Prediction step: state unchanged, covariance grows
        # P_pred = P + Q*I  (but we do it in-place to save alloc)
        P_diag_add = Q  # add to diagonal

        # Measurement: y_hat = x^T w
        y_hat = np.dot(w, x_buf)
        echo_est[n] = y_hat
        e = d[n] - y_hat
        output[n] = e

        # Innovation covariance: S = x^T (P + Q*I) x + R
        Px = P @ x_buf
        S = np.dot(x_buf, Px) + P_diag_add * np.dot(x_buf, x_buf) + R

        # Kalman gain: K = (P + Q*I) x / S
        K = (Px + P_diag_add * x_buf) / S

        # State update
        w += K * e

        # Covariance update: P = (I - K x^T)(P + Q*I)
        # Simplified: P_new = P + Q*I - K * (x^T (P + Q*I))
        Kx = np.outer(K, x_buf)
        P = P + P_diag_add * np.eye(n_taps) - Kx @ (P + P_diag_add * np.eye(n_taps))

        # Ensure symmetry (numerical stability)
        P = 0.5 * (P + P.T)

    return AECResult(
        output=AudioBuffer(samples=output.astype(np.float32), sample_rate=sr),
        echo_estimate=AudioBuffer(samples=echo_est.astype(np.float32), sample_rate=sr),
    )


def apply_aec(
    mic: AudioBuffer,
    ref: AudioBuffer,
    *,
    algorithm: str = "nlms",
    filter_length_ms: float = 200,
    step_size: float = 0.1,
    forgetting_factor: float = 0.999,
    process_noise: float = 1e-4,
    measurement_noise: float = 0.01,
    regularization: float = 1e-6,
) -> AECResult:
    """Dispatch to the chosen AEC algorithm.

    Args:
        algorithm: One of "nlms", "rls", "kalman".
        See individual functions for parameter descriptions.
    """
    if algorithm == "nlms":
        return aec_nlms(
            mic, ref,
            filter_length_ms=filter_length_ms,
            step_size=step_size,
            regularization=regularization,
        )
    elif algorithm == "rls":
        return aec_rls(
            mic, ref,
            filter_length_ms=filter_length_ms,
            forgetting_factor=forgetting_factor,
            regularization=regularization,
        )
    elif algorithm == "kalman":
        return aec_kalman(
            mic, ref,
            filter_length_ms=filter_length_ms,
            process_noise=process_noise,
            measurement_noise=measurement_noise,
            regularization=regularization,
        )
    else:
        raise ValueError(f"Unknown AEC algorithm: {algorithm!r}. Use 'nlms', 'rls', or 'kalman'.")
