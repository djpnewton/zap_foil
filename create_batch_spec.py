#!/usr/bin/env python3.7

import sys
import os
import json

batch_start = 1202
batch_end = 1351
batch_size = 10
zap_cents = 100

clump_size = 10

batch_allocations = (
        (80, 5),
        (10, 10),
        (10, 20))

batch_count = batch_end - (batch_start - 1)

print(f"batch count: {batch_count}\n")
print("batch allocations:")
batch_allocations_calc = []
total_zap = 0
for alloc in batch_allocations:
    percent, value = alloc
    num = int(percent/100.0 * batch_count)
    total_value = value * num * batch_size
    total_zap += total_value
    batch_allocations_calc.append((percent, value, num, total_value))
    print(f" - {percent}%, {value} ZAP, {num} batches, {total_value} ZAP total")

print(f"\ntotal zap: {total_zap}\n")

print(f"clump size: {clump_size}")
clumps = []
for alloc in batch_allocations_calc:
    percent, value, num, total_value = alloc
    num_per_clump = int(percent/100.0 * clump_size)
    for i in range(num_per_clump):
        clumps.append(value)
    print(f" - {num_per_clump} at, {value} ZAP")

batches = []
current_batch = batch_start
current_clump_index = 0
while current_batch <= batch_end:
    value = clumps[current_clump_index % len(clumps)]
    value *= zap_cents # convert to zap cents
    tx_fee = 1
    batches.append((current_batch, value + tx_fee))
    current_clump_index += 1
    current_batch += 1
total_zap = 0
for batch_index, value in batches:
    batch_zap = value/zap_cents * batch_size
    total_zap += batch_zap
print(f"\nCreated batches - total zap: {total_zap}\n")

filename = "batches.json"
with open(filename, "w") as f:
    json.dump(batches, f, indent=4)
print(f"Wrote batches to {filename}")
