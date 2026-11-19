# Gate 10 — physical edge/gateway/cloud testbed

Требуется работающий Docker Desktop. Из корня проекта:

```bash
python3 testbed/select_designs.py          # 36 архитектур (Pareto/dominated/boundary)
python3 testbed/run_testbed.py --repeats 3 # ~40-60 мин, пишет results/e9_testbed.csv
python3 testbed/analyze.py                 # MAPE, Spearman, Kendall, figures/fig7_testbed.png
```

Прогон можно прерывать: `run_testbed.py` дописывает CSV и пропускает уже
выполненные (design, repeat).

Что моделируется физически: отдельный контейнер на каждый edge/gateway/cloud
узел, по 1 CPU на контейнер (соответствует однопоточному серверу в модели),
CPU-работа стадии, равная w/C, реальные полезные нагрузки по сети и `tc netem`
(задержка + полоса) по классу канала; WAN до cloud — 20 мс / 200 Мбит/с.
Ограничение исследования: только конфигурации, помещающиеся на одну машину
(<= 4 edge + 2 gateway + 1 cloud).
