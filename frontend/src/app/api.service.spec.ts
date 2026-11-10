import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { ApiError, ApiService } from './api.service';
import { appConfig } from './app.config';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  });

  it('sends an answer in the shape the server expects', () => {
    api.answer(7, 2, 'worse', 900).subscribe();
    const request = http.expectOne('/api/insertions/7/answers/');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ question_index: 2, answer: 'worse', response_ms: 900 });
    request.flush({ done: true, position: 0, list: { id: 1, name: 'a', version: 1, entries: [] } });
  });

  it('starts an insertion with only the place name, so no tier is sent', () => {
    api.startInsertion(3, 'Bestia').subscribe();
    const request = http.expectOne('/api/lists/3/insertions/');
    expect(request.request.body).toEqual({ place_name: 'Bestia' });
    request.flush({ insertion_id: 1, question: null });
  });

  it("sends Django's CSRF header from Django's cookie", () => {
    document.cookie = 'csrftoken=abc123';
    api.createList('x').subscribe();
    const request = http.expectOne('/api/lists/');
    expect(request.request.headers.get('X-CSRFToken')).toBe('abc123');
    request.flush({ id: 1, name: 'x', version: 0, entries: [] });
  });

  it("maps a 409 to an ApiError carrying the server's code", async () => {
    const result = firstValueFrom(api.startInsertion(3, 'Bestia'));
    http
      .expectOne('/api/lists/3/insertions/')
      .flush({ code: 'list_changed' }, { status: 409, statusText: 'Conflict' });
    await expect(result).rejects.toEqual(new ApiError(409, 'list_changed'));
    await expect(result).rejects.toMatchObject({ status: 409, code: 'list_changed' });
  });

  it('gives other failures no code', async () => {
    const result = firstValueFrom(api.getLists());
    http
      .expectOne('/api/lists/')
      .flush({ code: 'not_a_conflict' }, { status: 500, statusText: 'Server Error' });
    await expect(result).rejects.toMatchObject({ status: 500, code: null });
  });
});
