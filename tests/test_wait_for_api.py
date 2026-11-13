# -*- coding: utf-8 -*-
"""Attente du redemarrage de l'API : reussite apres quelques echecs, ou delai depasse."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_window import wait_for_api


def _flaky(failures):
    calls = []

    def check(host):
        calls.append(host)
        if len(calls) <= failures:
            raise OSError("api down")

    return check, calls


def test_returns_true_as_soon_as_the_api_answers():
    check, calls = _flaky(failures=3)
    assert wait_for_api("http://h:1", timeout=5, interval=0, check=check, pump=lambda: None) is True
    assert calls == ["http://h:1"] * 4


def test_returns_false_when_the_api_never_answers():
    check, calls = _flaky(failures=10 ** 6)
    start = time.time()
    assert wait_for_api("http://h:1", timeout=0.1, interval=0, check=check, pump=lambda: time.sleep(0.01)) is False
    assert time.time() - start < 1 and calls


def test_pumps_events_while_waiting_and_respects_the_interval():
    check, calls = _flaky(failures=10 ** 6)
    pumps = []
    wait_for_api("h", timeout=0.3, interval=0.1, check=check, pump=lambda: (pumps.append(1), time.sleep(0.01)))
    assert len(pumps) > len(calls) >= 2     # l'interface est servie bien plus souvent que l'API n'est sondee
