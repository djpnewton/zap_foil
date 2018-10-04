#!/usr/bin/env python3

import sys
import argparse
import time
import re
import getpass
import datetime

import mnemonic
import pywaves as pw

from database import db_session, init_db
from models import Foil

TESTNET_NODE = "https://testnet1.wavesnodes.com"
MAINNET_NODE = "https://nodes.wavesnodes.com"

TESTNET_ASSETID = "CgUrFtinLXEbJwJVjwwcppk4Vpz1nMmR3H5cQaDcUcfe"
MAINNET_ASSETID = "nada"

EXIT_NO_COMMAND = 1
EXIT_SEED_INVALID = 10
EXIT_BALANCE_INSUFFICIENT = 11
EXIT_EXPIRY_INVALID = 12

def construct_parser():
    # construct argument parser
    parser = argparse.ArgumentParser()

    parser.add_argument("-m", "--mainnet", action="store_true", help="Set to use mainnet (default: false)")
    
    subparsers = parser.add_subparsers(dest="command")

    parser_create = subparsers.add_parser("create", help="Create foils")
    parser_create.add_argument("batchsize", metavar="BATCHSIZE", type=int, help="The number of foils to create in this batch")
    parser_create.add_argument("amount", metavar="AMOUNT", type=int, help="The amount of ZAP in each foil")

    parser_fund = subparsers.add_parser("fund", help="Fund foils")
    parser_fund.add_argument("batch", metavar="BATCH", type=int, help="The batch to fund")
    parser_fund.add_argument("-e", "--expiry", type=str, help="The expiry time to use (if you want to override the default - ie two months), number of seconds or '<X>days'")

    parser_show = subparsers.add_parser("show", help="Show foils")
    parser_show.add_argument("-b", "--batch", type=int, default=None, help="The batch to show")

    return parser

def create_run(args):
    # get free batch id
    batch = Foil.next_batch_id(db_session)

    # create foil
    for i in range(args.batchsize):
        # create entry in db
        date = time.time()
        addr = pw.Address()
        foil = Foil(date, batch, addr.privateKey, args.amount, None, None, None)
        db_session.add(foil)
        db_session.commit()

def fund_run(args):
    # get batch and calculate funds required
    foils = Foil.get_batch(db_session, args.batch)
    required_funds = 0
    for foil in foils:
        required_funds += foil.amount
    print(f"Required zap: {required_funds}")

    # get seed from user
    seed = getpass.getpass("Seed: ")

    # check seed is valid bip39 mnemonic
    m = mnemonic.Mnemonic("english")
    if m.check(seed.strip()):
        seed = seed.strip()
        seed = m.normalize_string(seed).split(" ")
        seed = " ".join(seed)
    else:
        a = input("Seed is not a valid bip39 mnemonic are you sure you wish to continue (y/N): ")
        if a not in ("y", "Y"):
            sys.exit(EXIT_SEED_INVALID)

    # create pywaves sender address
    sender = pw.Address(seed=seed)
    print(f"Account: {sender.address}")
    balance = sender.balance(assetId=args.assetid)
    print(f"Balance: {balance} ({args.assetid})")
    if balance < required_funds:
        print(f"ERROR: balance of account ({balance}) not great enough ({required_funds} required)")
        sys.exit(EXIT_BALANCE_INSUFFICIENT)

    # set expiry
    date = time.time()
    two_months = 60 * 60 * 24 * 30 * 2
    expiry = date + two_months
    if args.expiry:
        pattern = r"(\d+)days"
        m = re.search(pattern, args.expiry)
        if m:
            days = int(m.group(1))
            expiry = date + days * 60 * 60 * 24
        else:
            try:
                expiry = date + int(args.expiry)
            except:
                print("ERROR: expiry not a valid number")
                sys.exit(EXIT_EXPIRY_INVALID)
    dt = datetime.datetime.fromtimestamp(expiry)
    nice_expiry = dt.strftime("%Y/%m/%d %H:%M:%S")
    print(f"Batch expiry: {nice_expiry} ({expiry})")
    
    # add funds and expiry
    asset = pw.Asset(args.assetid)
    for foil in foils:
        addr = pw.Address(privateKey=foil.private_key)
        if foil.funding_txid:
            print(f"Skipping {addr.address}, funding_txid is not empty")
            continue
        balance = addr.balance(assetId=args.assetid)
        if balance > 0:
            print(f"Skipping {addr.address}, balance ({balance}) is not 0")
            continue
        result = sender.sendAsset(addr, asset, foil.amount)
        print(result)
        foil.expiry = expiry
        foil.funding_date = time.time()
        foil.funding_txid = result["id"]
        db_session.add(foil)
        db_session.commit()
        print(f"Funded {addr.address} with {foil.amount}")

def show_run(args):
    if args.batch or args.batch == 0:
        foils = Foil.get_batch(db_session, args.batch)
    else:
        foils = Foil.all(db_session)
    for foil in foils:
        print(foil.to_json())

if __name__ == "__main__":
    # parse arguments
    parser = construct_parser()
    args = parser.parse_args()

    # set chain and asset id
    pw.setNode(TESTNET_NODE, "testnet", "T")
    args.assetid = TESTNET_ASSETID
    if args.mainnet:
        pw.setNode(MAINNET_NODE, "mainnet", "W")
        args.assetid = MAINNET_ASSETID
    pw.setOnline()
    print(f"Network: {pw.NODE} ({pw.CHAIN} - {pw.CHAIN_ID})")

    # initialise database
    init_db()

    # set appropriate function
    function = None
    if args.command == "create":
        function = create_run
    elif args.command == "fund":
        function = fund_run
    elif args.command == "show":
        function = show_run
    else:
        parser.print_help()
        sys.exit(EXIT_NO_COMMAND)

    if function:
        function(args)
