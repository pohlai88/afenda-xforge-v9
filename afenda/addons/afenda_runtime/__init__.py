from . import controllers
from . import models
from .mail_templates import strip_invitation_marketing


def post_init_hook(env):
    strip_invitation_marketing(env)
