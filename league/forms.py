"""Server-side validation for public inputs."""

from django import forms

from .models import Auction, ContactEnquiry, Player, PlayerCategory, Tournament

MAX_RUPEES = 9_223_372_036_854_775_807


class SeasonFilterForm(forms.Form):
    season = forms.IntegerField(required=False, min_value=1, max_value=2147483647)


class ContactEnquiryForm(forms.ModelForm):
    class Meta:
        model = ContactEnquiry
        fields = ["name", "email", "phone", "subject", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}


class PlayerCategoryForm(forms.ModelForm):
    class Meta:
        model = PlayerCategory
        fields = ["name", "description", "base_price", "position"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class PlayerAuctionForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name", "city", "photo", "auction_category", "auction_base_price", "is_marquee", "in_auction_pool"]
        widgets = {"auction_base_price": forms.NumberInput(attrs={"min": 0, "step": 1})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["auction_category"].queryset = PlayerCategory.objects.order_by("position", "name")
        self.fields["auction_category"].required = False
        self.fields["auction_base_price"].required = False
        self.fields["auction_base_price"].help_text = "Leave blank to use the selected category's base price."


class AuctionCreateForm(forms.Form):
    name = forms.CharField(max_length=150)
    tournament = forms.ModelChoiceField(queryset=Tournament.objects.order_by("-season"))
    bid_increment = forms.IntegerField(min_value=1, max_value=MAX_RUPEES, initial=100000, help_text="Whole rupees; organisers can change this before starting.")
    team_budget = forms.IntegerField(min_value=1, max_value=MAX_RUPEES, help_text="Opening purse per team. Individual purses can be adjusted below.")
    players = forms.ModelMultipleChoiceField(queryset=Player.objects.none(), widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["players"].queryset = Player.objects.filter(
            is_active=True, in_auction_pool=True
        ).select_related("auction_category").order_by("auction_category__position", "name")
        current = Tournament.objects.filter(is_current=True).first()
        if current:
            self.fields["tournament"].initial = current.pk


class AuctionPurseForm(forms.Form):
    budget = forms.IntegerField(min_value=0, max_value=MAX_RUPEES, label="Purse budget (₹)")


class AuctionIncrementForm(forms.Form):
    bid_increment = forms.IntegerField(min_value=1, max_value=MAX_RUPEES, label="Bid increment (₹)")
