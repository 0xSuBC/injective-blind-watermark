# coding=utf-8
import cv2
import numpy as np


def cut_att_height(input_filename, output_file_name, ratio=0.8):
    input_img = cv2.imread(input_filename)
    input_img_shape = input_img.shape
    height = int(input_img_shape[0] * ratio)
    cv2.imwrite(output_file_name, input_img[:height, :, :])


def cut_att_width(input_filename, output_file_name, ratio=0.8):
    input_img = cv2.imread(input_filename)
    input_img_shape = input_img.shape
    width = int(input_img_shape[1] * ratio)
    cv2.imwrite(output_file_name, input_img[:, :width, :])


def cut_att(input_filename, output_file_name, o1=(0.2, 0.2), o2=(0.4, 0.5)):
    input_img = cv2.imread(input_filename)
    shape = input_img.shape
    x1, x2, y1, y2 = shape[0] * o1[0], shape[1] * o1[0], shape[0] * o2[0], shape[1] * o2[1]
    input_img[:int(x1), :] = 255
    input_img[int(x2):, :] = 255
    input_img[:, :int(y1)] = 255
    input_img[:, int(y2):] = 255
    cv2.imwrite(output_file_name, input_img)


def anti_cut_att(input_filename, output_file_name, origin_shape):
    input_img = cv2.imread(input_filename)
    output_img = input_img.copy()
    output_img_shape = output_img.shape

    if output_img_shape[0] < origin_shape[0]:
        output_img = np.concatenate(
            [output_img, 255 * np.ones((origin_shape[0] - output_img_shape[0], output_img_shape[1], 3))], axis=0)
        output_img_shape = output_img.shape

    if output_img_shape[1] < origin_shape[1]:
        output_img = np.concatenate(
            [output_img, 255 * np.ones((output_img_shape[0], origin_shape[1] - output_img_shape[1], 3))], axis=1)

    cv2.imwrite(output_file_name, output_img)


def resize_att(input_filename, output_file_name, out_shape=(500, 500)):
    input_img = cv2.imread(input_filename)
    output_img = cv2.resize(input_img, dsize=out_shape)
    cv2.imwrite(output_file_name, output_img)


def bright_att(input_filename, output_file_name, ratio=0.8):
    input_img = cv2.imread(input_filename)
    output_img = input_img * ratio
    output_img[output_img > 255] = 255
    cv2.imwrite(output_file_name, output_img)


def shelter_att(input_filename, output_file_name, ratio=0.1, n=3):
    input_img = cv2.imread(input_filename)
    input_img_shape = input_img.shape
    output_img = input_img.copy()
    for i in range(n):
        tmp = np.random.rand() * (1 - ratio)
        start_height, end_height = int(tmp * input_img_shape[0]), int((tmp + ratio) * input_img_shape[0])
        tmp = np.random.rand() * (1 - ratio)
        start_width, end_width = int(tmp * input_img_shape[1]), int((tmp + ratio) * input_img_shape[1])
        output_img[start_height:end_height, start_width:end_width, :] = 255
    cv2.imwrite(output_file_name, output_img)


def salt_pepper_att(input_filename, output_file_name, ratio=0.01):
    input_img = cv2.imread(input_filename)
    input_img_shape = input_img.shape
    output_img = input_img.copy()
    for i in range(input_img_shape[0]):
        for j in range(input_img_shape[1]):
            if np.random.rand() < ratio:
                output_img[i, j, :] = 255
    cv2.imwrite(output_file_name, output_img)


def rot_att(input_filename, output_file_name, angle=45):
    input_img = cv2.imread(input_filename)
    rows, cols, _ = input_img.shape
    M = cv2.getRotationMatrix2D(center=(cols / 2, rows / 2), angle=angle, scale=1)
    output_img = cv2.warpAffine(input_img, M, (cols, rows))
    cv2.imwrite(output_file_name, output_img)
