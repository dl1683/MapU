"""SQLAlchemy models — import all for Alembic metadata discovery."""

from mapu.models.attestation import Attestation, AttestationSituation
from mapu.models.audit import Activity
from mapu.models.authority import SourcePolicyEval
from mapu.models.computation import ComputationRun, ComputationSpec
from mapu.models.context import QueryView, Situation
from mapu.models.corpus import Corpus
from mapu.models.entity import Handle, IdentityDecisionModel
from mapu.models.evidence import (
    Chunk,
    ChunkEmbedding,
    DocumentExpression,
    DocumentWork,
    StructureNode,
    TextSpan,
)
from mapu.models.gap import Gap, GapTarget
from mapu.models.lineage import DerivationEdge, SupersessionEdge
from mapu.models.proposition import Proposition, PropositionParticipant
from mapu.models.review import Changeset, ChangesetOperation
from mapu.models.truth import PropositionState, PropositionStateBasis

__all__ = [
    "Activity",
    "Attestation",
    "AttestationSituation",
    "Changeset",
    "ChangesetOperation",
    "Chunk",
    "ChunkEmbedding",
    "ComputationRun",
    "ComputationSpec",
    "Corpus",
    "DerivationEdge",
    "DocumentExpression",
    "DocumentWork",
    "Gap",
    "GapTarget",
    "Handle",
    "IdentityDecisionModel",
    "Proposition",
    "PropositionParticipant",
    "PropositionState",
    "PropositionStateBasis",
    "QueryView",
    "Situation",
    "SourcePolicyEval",
    "StructureNode",
    "SupersessionEdge",
    "TextSpan",
]
