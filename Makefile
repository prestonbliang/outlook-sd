PY = uv run python -m

probe:
	$(PY) pipeline.probes.run_all

history:
	$(PY) pipeline.history $(SOURCES)

train:
	$(PY) models.train_flood
	$(PY) models.train_heat
	$(PY) models.train_water
	$(PY) models.train_air
	$(PY) models.train_fire

api:
	uv run uvicorn api.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	uv run pytest -q tests
	cd web && npx playwright test

.PHONY: probe history train api web test
