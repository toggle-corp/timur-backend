import typing

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from apps.user.models import User


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom Adapter to store additional data to user from provider
    """

    def _save_additional_user_data(self, user, sociallogin):
        extra_data = sociallogin.account.extra_data

        new_picture_url = extra_data.get("picture")
        if new_picture_url:
            user.display_picture = new_picture_url

        if user.pk:
            user.save(update_fields=("display_picture",))

    @typing.override
    def new_user(self, request, sociallogin):
        new_user = super().new_user(request, sociallogin)
        self._save_additional_user_data(new_user, sociallogin)
        return new_user

    @typing.override
    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)
        # Only handle auto-linking and email registration for Google
        if sociallogin.account.provider != "google":
            return

        user_email = sociallogin.account.extra_data.get("email")
        if not user_email:
            return

        try:
            existing_user = User.objects.get(email=user_email)
            self._save_additional_user_data(existing_user, sociallogin)
        except User.DoesNotExist:
            return
