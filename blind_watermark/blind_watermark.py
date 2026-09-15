#!/usr/bin/env python3
# coding=utf-8
import numpy as np
import cv2
from .bwm_core import WaterMarkCore


class WaterMark:
    def __init__(self, password_wm=1, password_img=1, block_shape=(4, 4), mode='common', processes=None):
        self.bwm_core = WaterMarkCore(password_img=password_img, mode=mode, processes=processes)
        self.password_wm = password_wm
        self.wm_size = 0

    def read_img(self, filename):
        self.bwm_core.read_img(filename=filename)

    def read_img_wm(self, filename):
        wm = cv2.imread(filename)
        if wm is None:
            raise IOError("file '{filename}' not read".format(filename=filename))
        self.wm = wm[:, :, 0]
        self.wm_bit = self.wm.flatten() > 128

    def read_wm(self, wm_content, mode='img'):
        if mode == 'img':
            self.read_img_wm(filename=wm_content)
        elif mode == 'str':
            raw_bytes = wm_content.encode('utf-8')
            bits_str = ''.join(format(b, '08b') for b in raw_bytes)
            self.wm_bit = (np.array(list(bits_str)) == '1')
        else:
            self.wm_bit = np.array(wm_content)

        self.wm_size = self.wm_bit.size
        np.random.RandomState(self.password_wm).shuffle(self.wm_bit)
        self.bwm_core.read_wm(self.wm_bit)

    def embed(self, filename):
        self.bwm_core.embed(filename=filename)

    def extract_decrypt(self, wm_avg):
        wm_index = np.arange(self.wm_size)
        np.random.RandomState(self.password_wm).shuffle(wm_index)
        wm_avg[wm_index] = wm_avg.copy()
        return wm_avg

    def extract(self, filename, wm_shape, out_wm_name=None, mode='img'):
        self.wm_size = np.array(wm_shape).prod()

        if mode in ('str', 'bit'):
            wm_avg = self.bwm_core.extract_with_kmeans(filename=filename, wm_shape=wm_shape)
        else:
            wm_avg = self.bwm_core.extract(filename=filename, wm_shape=wm_shape)

        wm = self.extract_decrypt(wm_avg=wm_avg)

        if mode == 'img':
            cv2.imwrite(out_wm_name, 255 * wm.reshape(wm_shape[0], wm_shape[1]))
        elif mode == 'str':
            bits_arr = (np.round(wm)).astype(np.uint8)
            n_bytes = len(bits_arr) // 8
            byte_list = []
            for i in range(n_bytes):
                chunk = bits_arr[i * 8: (i + 1) * 8]
                b = 0
                for bit in chunk:
                    b = (b << 1) | int(bit)
                byte_list.append(b)
            try:
                wm = bytes(byte_list).decode('utf-8', errors='replace').rstrip('\x00')
            except Exception:
                wm = ''

        return wm
