import pytest
import torch
from torch import nn

from torchgpipe import GPipe
from torchgpipe.skip import pop, skippable, stash
from torchgpipe.skip.portal import PortalBlue, PortalCopy, PortalOrange


@pytest.mark.skipif(not torch.cuda.is_available(), reason='cuda required')
@pytest.mark.parametrize('balance', [[3], [1, 2], [2, 1], [1, 1, 1]],
                         ids=['3', '1:2', '2:1', '1:1:1'])
@pytest.mark.parametrize('checkpoint', ['never', 'always', 'except_last'])
def test_1to3(balance, checkpoint):
    if torch.cuda.device_count() < len(balance):
        pytest.skip('at least %d cuda devices required' % len(balance))

    @skippable(stash=['1to3'])
    class Layer1(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Conv2d(3, 3, 1)

        def forward(self, input):
            yield stash('1to3', input)
            output = self.conv(input)
            return output

    class Layer2(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Conv2d(3, 3, 1)

        def forward(self, input):
            output = self.conv(input)
            return output

    @skippable(pop=['1to3'])
    class Layer3(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Conv2d(3, 3, 1)

        def forward(self, input):
            skip_1to3 = yield pop('1to3')
            output = self.conv(input) + skip_1to3
            return output

    model = nn.Sequential(Layer1(), Layer2(), Layer3())
    model = GPipe(model, balance, chunks=3, checkpoint=checkpoint)

    in_device = model.devices[0]
    out_device = model.devices[-1]

    input = torch.rand(30, 3, 224, 224, device=in_device, requires_grad=True)
    output = model(input)
    loss = output.mean()
    loss.backward()

    assert torch.allclose(output.norm(), torch.tensor(1039.159, device=out_device), atol=1.0)
    assert torch.allclose(input.grad.norm(), torch.tensor(0.0004533053, device=in_device), atol=10**-5)


def test_none_skip():
    @skippable(stash=['none'])
    class Stash(nn.Module):
        def forward(self, input):
            yield stash('none', None)
            return input

    @skippable(pop=['none'])
    class Pop(nn.Module):
        def forward(self, input):
            none = yield pop('none')
            assert none is None
            return input

    model = nn.Sequential(Stash(), Pop())
    model = GPipe(model, [1, 1], devices=['cpu', 'cpu'], chunks=5)

    input = torch.rand(10, requires_grad=True)
    output = model(input)

    def assert_grad_fn_is_not_portal(grad_fn, visited=set()):
        if grad_fn in visited or grad_fn is None:
            return

        assert not isinstance(grad_fn, PortalBlue._backward_cls)
        assert not isinstance(grad_fn, PortalCopy._backward_cls)
        assert not isinstance(grad_fn, PortalOrange._backward_cls)

        visited.add(grad_fn)
        for next_grad_fn, _ in grad_fn.next_functions:
            assert_grad_fn_is_not_portal(next_grad_fn, visited)

    assert_grad_fn_is_not_portal(output.grad_fn)

    output.sum().backward()
    assert input.grad.mean().item() == 1
