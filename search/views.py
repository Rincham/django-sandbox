import time

from django.contrib.postgres.search import SearchRank
from django.db.models import F
from django.views.generic import ListView

from search.forms import SearchForm
from search.highlight import highlight, snippet
from search.models import Document
from search.query import QueryError, compile_query, parse_query


class SearchView(ListView):
    model = Document
    paginate_by = 20
    template_name = 'search/index.html'

    def get(self, request, *args, **kwargs):
        self.form = SearchForm(request.GET or None)
        self.compiled = self._compile_query()
        self.started = time.perf_counter()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if self.compiled is None:
            return Document.objects.none()
        documents = Document.objects.filter(search_vector=self.compiled.search_query)
        if source := self.form.cleaned_data['source']:
            documents = documents.filter(source=source)
        return (
            documents.annotate(rank=SearchRank(F('search_vector'), self.compiled.search_query))
            .order_by('-rank', '-updated_at', '-pk')
            .only('pk', 'title', 'body', 'source', 'source_id', 'updated_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(form=self.form, compiled=self.compiled)
        if self.compiled is not None:
            # 件数の取得と 1 ページ分の取得をここで済ませ、検索にかかった時間に含める
            hits = context['paginator'].count
            documents = list(context['object_list'])
            elapsed_ms = (time.perf_counter() - self.started) * 1000
            terms = self.compiled.highlight_terms
            results = [
                {
                    'document': document,
                    'title': highlight(document.title, terms),
                    'snippet': snippet(document.body, terms),
                }
                for document in documents
            ]
            context.update(hits=hits, results=results, elapsed_ms=elapsed_ms)
        return context

    def _compile_query(self):
        if not self.form.is_valid() or not self.form.cleaned_data['q'].strip():
            return None
        try:
            return compile_query(parse_query(self.form.cleaned_data['q']))
        except QueryError as e:
            self.form.add_error(None, str(e))
            return None
