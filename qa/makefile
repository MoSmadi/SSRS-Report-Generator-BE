.PHONY: all smoke contracts

export $(shell sed 's/=.*//' .env 2>/dev/null)

all: smoke contracts

smoke:
	python3 smoke_check.py

contracts:
	pytest -q
