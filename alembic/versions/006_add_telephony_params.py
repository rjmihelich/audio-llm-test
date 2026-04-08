"""Add telephony pipeline parameters to sweep_configs and test_cases.

Revision ID: 006
Revises: 005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------------
    # sweep_configs — telephony sweep dimension columns
    # ---------------------------------------------------------------------------
    op.add_column(
        "sweep_configs",
        sa.Column(
            "bt_codec_types",
            JSON(),
            nullable=True,
            comment='BT HFP codec types to sweep, e.g. ["cvsd", "msbc", "none"]',
        ),
    )
    op.add_column(
        "sweep_configs",
        sa.Column(
            "agc_configs",
            JSON(),
            nullable=True,
            comment='AGC preset names to sweep, e.g. ["off", "mild", "aggressive"]',
        ),
    )
    op.add_column(
        "sweep_configs",
        sa.Column(
            "aec_residual_configs",
            JSON(),
            nullable=True,
            comment="List of AEC residual config dicts to sweep",
        ),
    )
    op.add_column(
        "sweep_configs",
        sa.Column(
            "network_configs",
            JSON(),
            nullable=True,
            comment="List of network degradation config dicts to sweep",
        ),
    )
    op.add_column(
        "sweep_configs",
        sa.Column(
            "telephony_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Whether this sweep uses the telephony pipeline",
        ),
    )

    # ---------------------------------------------------------------------------
    # test_cases — per-case telephony parameter columns
    # ---------------------------------------------------------------------------
    op.add_column(
        "test_cases",
        sa.Column(
            "bt_codec",
            sa.String(50),
            nullable=True,
            comment="BT HFP codec for this test case: cvsd, msbc, or none",
        ),
    )
    op.add_column(
        "test_cases",
        sa.Column(
            "agc_config_json",
            JSON(),
            nullable=True,
            comment="AGC configuration for this test case (serialized AGCConfig)",
        ),
    )
    op.add_column(
        "test_cases",
        sa.Column(
            "aec_residual_config_json",
            JSON(),
            nullable=True,
            comment="AEC residual configuration for this test case",
        ),
    )
    op.add_column(
        "test_cases",
        sa.Column(
            "network_config_json",
            JSON(),
            nullable=True,
            comment="Network degradation configuration for this test case",
        ),
    )

    # ---------------------------------------------------------------------------
    # Extend pipeline_enum to include 'telephony'
    # The enum type is stored as VARCHAR with native_enum=False, so we just
    # update the check constraint if one exists — on most setups this is
    # enforced at the application layer only.
    # ---------------------------------------------------------------------------
    # No DDL change needed for non-native enum (native_enum=False in model).


def downgrade() -> None:
    op.drop_column("test_cases", "network_config_json")
    op.drop_column("test_cases", "aec_residual_config_json")
    op.drop_column("test_cases", "agc_config_json")
    op.drop_column("test_cases", "bt_codec")

    op.drop_column("sweep_configs", "telephony_enabled")
    op.drop_column("sweep_configs", "network_configs")
    op.drop_column("sweep_configs", "aec_residual_configs")
    op.drop_column("sweep_configs", "agc_configs")
    op.drop_column("sweep_configs", "bt_codec_types")
