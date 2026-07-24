from fastapi import APIRouter

from services.global_macro_commentary_service import get_region_commentary
from services.macro_data_service import list_regions

router = APIRouter()


@router.get("/global-macro/regions")
def global_macro_regions():
    """List the 10 regions covered by the global macro+news commentary
    layer (see services/macro_data_service.REGIONS for the full
    definitions, including which World Bank proxy country backs each
    multi-country grouping)."""
    return {"regions": list_regions()}


@router.get("/global-macro/{region}")
def global_macro_region(region: str, lang: str = "zh-HK"):
    """Combined macro indicators + filtered news + FinBERT sentiment + AI
    commentary for one region. See
    services/global_macro_commentary_service.get_region_commentary() for
    the honesty/degradation contract -- pieces that are unavailable (e.g.
    Taiwan has no World Bank macro data) are marked as such rather than
    causing the whole response to fail."""
    return get_region_commentary(region, lang=lang)
