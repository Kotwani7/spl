import pytest
from django.urls import reverse

from league.models import ContactEnquiry


@pytest.mark.django_db
@pytest.mark.parametrize("values", [
    {},
    {"name": " ", "email": "person@example.com", "message": "Hello"},
    {"name": "Person", "email": "not-an-email", "message": "Hello"},
    {"name": "x" * 121, "email": "person@example.com", "message": "Hello"},
    {"name": "Person", "email": "person@example.com", "message": " "},
])
def test_invalid_contact_enquiries_are_not_saved(client, values):
    response = client.post(reverse("contact"), values)
    assert response.status_code == 200
    assert ContactEnquiry.objects.count() == 0
    assert response.context["form"].errors


@pytest.mark.django_db
def test_valid_contact_enquiry_is_saved(client):
    response = client.post(reverse("contact"), {
        "name": " Test person ", "email": "person@example.com",
        "phone": "", "subject": "Registration", "message": " Please contact me. ",
    })
    assert response.status_code == 302
    enquiry = ContactEnquiry.objects.get()
    assert enquiry.name == "Test person"
    assert enquiry.message == "Please contact me."


@pytest.mark.django_db
def test_notification_failure_does_not_lose_enquiry(client, settings, monkeypatch):
    settings.EMAIL_HOST_USER = "test-smtp-user"
    settings.EMAIL_HOST_PASSWORD = "test-smtp-password"

    def unavailable(*args, **kwargs):
        raise OSError("SMTP unavailable")

    monkeypatch.setattr("league.views.send_mail", unavailable)
    response = client.post(reverse("contact"), {
        "name": "Test person", "email": "person@example.com", "message": "Hello",
    })
    assert response.status_code == 302
    assert ContactEnquiry.objects.count() == 1
