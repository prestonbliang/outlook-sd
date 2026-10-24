PY = uv run python -m

doctor:
	python scripts/check_setup.py

init:
	$(PY) api.export

refresh:
	$(PY) pipeline.run_all
	$(PY) api.export

build:
	$(PY) api.export
	cd web && npm run build

package:
	node scripts/prepare-vercel.mjs

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
	cd web && npm run test:unit
	cd web && npx playwright test

.PHONY: doctor init refresh build package probe history train api web test
