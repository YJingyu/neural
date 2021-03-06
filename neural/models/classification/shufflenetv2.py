from collections import OrderedDict

import torch
from torch import nn


__all__ = [
    'ShuffleNetV2',
    'shufflenetv2_x0_5', 'shufflenetv2_x1_0',
    'shufflenetv2_x1_5', 'shufflenetv2_x2_0',
]


def shufflenetv2_x0_5(in_channels, num_classes):
    return ShuffleNetV2(in_channels, num_classes,
                        block_depth=[4, 8, 4],
                        block_channels=[24, 48, 96, 192, 1024])


def shufflenetv2_x1_0(in_channels, num_classes):
    return ShuffleNetV2(in_channels, num_classes,
                        block_depth=[4, 8, 4],
                        block_channels=[24, 116, 232, 464, 1024])


def shufflenetv2_x1_5(in_channels, num_classes):
    return ShuffleNetV2(in_channels, num_classes,
                        block_depth=[4, 8, 4],
                        block_channels=[24, 176, 352, 704, 1024])


def shufflenetv2_x2_0(in_channels, num_classes):
    return ShuffleNetV2(in_channels, num_classes,
                        block_depth=[4, 8, 4],
                        block_channels=[24, 244, 488, 976, 2048])


class ShuffleNetV2(nn.Sequential):

    def __init__(self, in_channels, num_classes, block_depth, block_channels):
        features = nn.Sequential(OrderedDict([
            ('head', nn.Sequential(
                ConvBlock(in_channels, block_channels[0], 3,
                          padding=1, stride=2),
                nn.MaxPool2d(kernel_size=3, stride=2, padding=1),
            )),
            ('layer1', make_layer(
                block_channels[0], block_channels[1], block_depth[0])),
            ('layer2', make_layer(
                block_channels[1], block_channels[2], block_depth[1])),
            ('layer3', make_layer(
                block_channels[2], block_channels[3], block_depth[2])),
            ('tail', ConvBlock(block_channels[3], block_channels[4], 1)),
        ]))

        classifier = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(block_channels[4], num_classes)
        )

        super().__init__(OrderedDict([
            ('features', features),
            ('classifier', classifier),
        ]))


def make_layer(in_channels, out_channels, depth, stride=2):
    layers = [InvertedResidualBlock(in_channels, out_channels, stride=stride)]
    for _ in range(1, depth):
        layers += [InvertedResidualBlock(out_channels, out_channels)]
    return nn.Sequential(*layers)


class InvertedResidualBlock(nn.Module):

    def __init__(self, in_channels, out_channels, stride=1):
        super().__init__()

        branch_channels = out_channels // 2

        self.left = (
            DSConvBlock(in_channels, branch_channels, 3,
                        padding=1, stride=stride)
            if stride > 1 else None)
        self.right = nn.Sequential(
            ConvBlock(
                in_channels if stride > 1 else branch_channels,
                branch_channels, 1),
            DSConvBlock(branch_channels, branch_channels,
                        kernel_size=3, padding=1, stride=stride),
        )

    def forward(self, input):
        if self.left is None:
            left, right = input.chunk(2, dim=1)
            right = self.right(right)
        else:
            left = self.left(input)
            right = self.right(input)

        x = torch.cat([left, right], dim=1)
        return channel_shuffle(x, 2)


def ConvBlock(in_channels, out_channels, kernel_size,
              padding=0, stride=1,
              use_relu=True):
    layers = [
        nn.Conv2d(in_channels, out_channels, kernel_size,
                  padding=padding, stride=stride, bias=False),
        nn.BatchNorm2d(out_channels)
    ]
    if use_relu:
        layers += [nn.ReLU(inplace=True)]
    return nn.Sequential(*layers)


def DSConvBlock(in_channels, out_channels, kernel_size,
                padding=0, stride=1,
                use_relu=True):
    layers = [
        nn.Conv2d(in_channels, in_channels, kernel_size,
                  padding=padding, stride=stride, groups=in_channels,
                  bias=False),
        nn.BatchNorm2d(in_channels),
        nn.Conv2d(in_channels, out_channels, 1, bias=False),
        nn.BatchNorm2d(out_channels),
    ]
    if use_relu:
        layers += [nn.ReLU(inplace=True)]
    return nn.Sequential(*layers)


def channel_shuffle(x, groups):
    batch_size, channels, height, width = x.shape

    return x \
        .reshape(batch_size, groups, channels // groups, height, width) \
        .transpose(1, 2) \
        .reshape(batch_size, channels, height, width)
