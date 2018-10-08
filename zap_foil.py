#!/usr/bin/env python3

import sys
import os
import argparse
import time
import re
import getpass
import datetime
import decimal

import requests
import mnemonic
import pywaves as pw
import qrcode
import PIL
from PIL import ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch, cm

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
EXIT_INVALID_RECIPIENT = 13

def get_asset_fee(assetid):
    url = f"{pw.NODE}/assets/details/{assetid}";
    response = requests.get(url).json()
    min_asset_fee = response["minSponsoredAssetFee"]
    return min_asset_fee

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

    parser_images = subparsers.add_parser("images", help="Create qrcode images")

    parser_sweep = subparsers.add_parser("sweep", help="Sweep expired foils")
    parser_sweep.add_argument("recipient", metavar="RECIPIENT", type=str, help="The recipient of the swept funds")

    return parser

def create_run(args):
    # get free batch id
    batch = Foil.next_batch_id(db_session)

    # create foil
    for i in range(args.batchsize):
        # create entry in db
        date = time.time()
        addr = pw.Address()
        foil = Foil(date, batch, addr.seed, args.amount, None, None, None)
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
        addr = pw.Address(seed=foil.seed)
        if foil.funding_txid:
            print(f"Skipping {addr.address}, funding_txid is not empty")
            continue
        balance = addr.balance(assetId=args.assetid)
        if balance > 0:
            print(f"Skipping {addr.address}, balance ({balance}) is not 0")
            continue
        result = sender.sendAsset(addr, asset, foil.amount)
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

def images_run(args):
    # consts
    dpi = 300
    mm_per_in = 25.4

    # page size
    width_mm = 210
    height_mm = 297
    width_in = width_mm / mm_per_in
    height_in = height_mm / mm_per_in
    width = width_in * dpi
    height = height_in * dpi

    # qrcode width and y position
    qrcode_y_mm = 50
    qrcode_width_mm = 100

    # calc qrcode pix values
    qrcode_y = qrcode_y_mm / mm_per_in * dpi
    qrcode_width = qrcode_width_mm / mm_per_in * dpi
    qrcode_x = (width / 2) - (qrcode_width / 2)
    qrcode_border = 4
    qrcode_boxes = 30 + qrcode_border + qrcode_border
    qrcode_box_size = int(qrcode_width / qrcode_boxes)

    # batch text
    font_size = 50
    font = ImageFont.truetype("Andale Mono.ttf", font_size)
    text_y_mm = 250
    text_y = text_y_mm / mm_per_in * dpi

    # create image directory
    path = "images"
    if not os.path.exists(path):
        os.makedirs(path)

    # create pdf
    fn = os.path.join(path, "images.pdf")
    pdf = canvas.Canvas(fn, pagesize=(width_mm, height_mm))

    foils = Foil.all(db_session)
    for foil in foils:
        filename = f"b{foil.batch}_{foil.id}.png"
        filename = os.path.join(path, filename)

        # create qr code image
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, \
            box_size=qrcode_box_size, border=qrcode_border)
        qr.add_data(foil.seed)
        qr.make()
        qr_img = qr.make_image(fill_color="black", back_color="transparent")

        # create template image
        template = PIL.Image.new("RGBA", (int(width), int(height)))
        # draw batch text
        d = PIL.ImageDraw.Draw(template)
        text = f"b{foil.batch}"
        text_width = font.getsize(text)[0]
        text_x = (width / 2) - (text_width / 2)
        d.text((int(text_x), int(text_y)), text, font=font, fill="black")
        # paste qr code
        template.paste(qr_img, (int(qrcode_x), int(qrcode_y)))

        # save image
        print(filename)
        template.save(filename)

        # add page to pdf
        pdf.drawImage(filename, 0, 0, width_mm, height_mm, mask="auto")
        pdf.showPage()

    # save pdf
    print("saving pdf..")
    pdf.save()

def sweep_run(args):
    # check recipient is a valid address
    if not pw.validateAddress(args.recipient):
        print(f"ERROR: {args.recipient} is not a valid address")
        sys.exit(EXIT_INVALID_RECIPIENT)
    recipient = pw.Address(args.recipient)

    # sweep expired foils
    asset = pw.Asset(args.assetid)
    asset_fee = get_asset_fee(args.assetid)
    date = time.time()
    foils = Foil.all(db_session)
    for foil in foils:
        if foil.expiry and date >= foil.expiry:
            addr = pw.Address(seed=foil.seed)
            balance = addr.balance(assetId=args.assetid)
            if balance == 0:
                print(f"Skipping {addr.address}, balance is 0")
                continue
            result = addr.sendAsset(recipient, asset, balance - asset_fee, \
                feeAsset=asset, txFee=asset_fee)
            print(result)
            print(f"Swept {addr.address}, txid {result['id']}")

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
    elif args.command == "images":
        function = images_run
    elif args.command == "sweep":
        function = sweep_run
    else:
        parser.print_help()
        sys.exit(EXIT_NO_COMMAND)

    if function:
        function(args)
