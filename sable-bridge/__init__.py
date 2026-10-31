"""sable-bridge - ask the owned local Sable-01 model short questions.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
"""
from __future__ import annotations

from . import schemas, tools


def register(ctx):
    ctx.register_tool(
        name="ask_sable",
        toolset="sable",
        schema=schemas.ASK_SABLE,
        handler=tools.ask_sable,
    )
