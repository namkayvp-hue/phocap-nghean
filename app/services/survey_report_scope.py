"""Report figures include households whose investigation is complete."""
from app.survey_models import SurveyForm

COMPLETED_SURVEY_STATUSES = ('DA_HOAN_THANH', 'DA_DUYET')


def completed_survey_forms():
    return SurveyForm.status.in_(COMPLETED_SURVEY_STATUSES)
