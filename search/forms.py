from django import forms

from search.models import Document


class SearchForm(forms.Form):
    q = forms.CharField(
        label='キーワード',
        max_length=200,
        required=False,
        help_text=(
            '空白で区切った語をすべて含む文書を探します。'
            '"…" でフレーズ、-語 で除外、語 OR 語 でいずれかを含む文書を探します。'
        ),
        widget=forms.TextInput(attrs={'type': 'search', 'autofocus': True}),
    )
    source = forms.ChoiceField(label='出典', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sources = Document.objects.exclude(source='').values_list('source', flat=True).distinct().order_by('source')
        self.fields['source'].choices = [('', 'すべて'), *((source, source) for source in sources)]
