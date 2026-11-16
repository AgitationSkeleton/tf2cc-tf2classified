"""Revision tag for generated client assets (tools/ASSET_REV).

Clients only download files they do not already have, so a regenerated model
under an unchanged path never reaches players who cached the old one. Bump
ASSET_REV whenever generated models change: every generator writes into
revision-named folders (models/player/tf2cc/variants_<rev>,
models/weapons/tf2cc_<rev>) and rewrites the configs that point at them.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
REV = open(os.path.join(_HERE, "ASSET_REV")).read().strip()
# The player-model variants can be revised on their own (ASSET_REV_VARIANTS) so
# a variant-only fix does not make clients re-download every viewmodel.
_VREV = os.path.join(_HERE, "ASSET_REV_VARIANTS")
VARIANTS_REV = open(_VREV).read().strip() if os.path.exists(_VREV) else REV
VARIANTS_REL = "models/player/tf2cc/variants_%s" % VARIANTS_REV
VIEWMODELS_REL = "models/weapons/tf2cc_%s" % REV
