"""
Applier Factory.
Selects the appropriate ATS applier based on job URL.
"""

from typing import Optional, List
from src.applier.base import BaseApplier
from src.applier.greenhouse import GreenhouseApplier
from src.applier.lever import LeverApplier
from src.applier.indeed import IndeedApplier
from src.applier.naukri import NaukriApplier
from src.applier.universal_company_applier import UniversalCompanyApplier
from src.models import CandidateProfile


def get_applier_for_url(url: str, profile: CandidateProfile, **kwargs) -> Optional[BaseApplier]:
    """
    Returns an instantiated Applier suitable for the target URL, or None if unsupported.
    """
    appliers = [
        NaukriApplier(profile, **kwargs),
        IndeedApplier(profile, **kwargs),
        GreenhouseApplier(profile, **kwargs),
        LeverApplier(profile, **kwargs),
        UniversalCompanyApplier(profile, **kwargs),
    ]

    for applier in appliers:
        if applier.can_handle(url):
            return applier

    return None
