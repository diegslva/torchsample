"""
Utility functions for torch.Tensors
"""

import pickle
import torch

import numpy as np


def th_allclose(x, y):
    """
    Determine whether two torch tensors have same values
    Mimics np.allclose
    """
    return torch.sum(torch.abs(x-y)) < 1e-5


def th_flatten(x):
    """Flatten tensor"""
    return x.contiguous().view(-1)


def th_c_flatten(x):
    """
    Flatten tensor, leaving channel intact.
    Assumes CHW format.
    """
    return x.contiguous().view(x.size(0), -1)


def th_bc_flatten(x):
    """
    Flatten tensor, leaving batch and channel dims intact.
    Assumes BCHW format
    """
    return x.contiguous().view(x.size(0), x.size(1), -1)


def th_iterproduct(*args):
    return torch.from_numpy(np.indices(args).reshape((len(args),-1)).T)


def th_iterproduct_like(x):
    return th_iterproduct(*x.size())


def th_gather_nd(x, coords):
    inds = coords.mv(torch.LongTensor(x.stride()))
    x_gather = torch.index_select(th_flatten(x), 0, inds)
    return x_gather


def th_affine_2d(x, matrix, mode='bilinear', center=True):
    """
    2D Affine image transform on torch.Tensor
    
    Arguments
    ---------
    x : torch.Tensor of size (C, H, W)
        image tensor to be transformed

    matrix : torch.Tensor of size (3, 3) or (2, 3)
        transformation matrix

    mode : string in {'nearest', 'bilinear'}
        interpolation scheme to use

    center : boolean
        whether to alter the bias of the transform 
        so the transform is applied about the center
        of the image rather than the origin

    Example
    ------- 289
    >>> x = torch.zeros(1,2000,2000)
    >>> x[:,100:1500,100:500] = 10*torch.rand(1,1400,400)
    >>> matrix = torch.FloatTensor([[1.,0,-300],
    ...                             [0,1.,-300]])
    >>> #xn = th_affine_2d(x, matrix, mode='nearest')
    >>> xb = th_affine_2d(x, matrix, mode='bilinear')

    """
    A = matrix[:2,:2]
    b = matrix[:2,2]

    # make a meshgrid of normal coordinates
    coords = th_iterproduct(x.size(1),x.size(2)).float()

    if center:
        # shift the coordinates so center is the origin
        coords[:,0] = coords[:,0] - (x.size(1) / 2. + 0.5)
        coords[:,1] = coords[:,1] - (x.size(2) / 2. + 0.5)
    
    # apply the coordinate transformation
    new_coords = coords.mm(A.t().contiguous()) + b.expand_as(coords)

    if center:
        # shift the coordinates back so origin is origin
        new_coords[:,0] = new_coords[:,0] + (x.size(1) / 2. + 0.5)
        new_coords[:,1] = new_coords[:,1] + (x.size(2) / 2. + 0.5)

    # map new coordinates using bilinear interpolation
    if mode == 'nearest':
        x_transformed = th_nearest_interp_2d(x, new_coords)
    elif mode == 'bilinear':
        x_transformed = th_bilinear_interp_2d(x, new_coords)

    return x_transformed


def th_nearest_interp_2d(input, coords):
    """
    2d nearest neighbor interpolation torch.Tensor
    """
    # take clamp of coords so they're in the image bounds
    coords[:,0] = torch.clamp(coords[:,0], 0, input.size(1)-1).round()
    coords[:,1] = torch.clamp(coords[:,1], 0, input.size(2)-1).round()

    stride = torch.FloatTensor(input.stride())[1:]
    idx = coords.mv(stride).long()

    input_flat = th_c_flatten(input)

    mapped_vals = torch.stack([input_flat[i][idx] 
                    for i in range(input.size(0))], 0)

    return mapped_vals.view_as(input)


def th_bilinear_interp_2d(input, coords):
    """
    trilinear interpolation of 3D torch.Tensor image
    """
    # take clamp then floor/ceil of x coords
    x = torch.clamp(coords[:,0], 0, input.size(1)-2)
    x0 = x.floor()
    x1 = x0 + 1
    # take clamp then floor/ceil of y coords
    y = torch.clamp(coords[:,1], 0, input.size(2)-2)
    y0 = y.floor()
    y1 = y0 + 1

    xd = x - x0
    yd = y - y0

    stride = torch.LongTensor(input.stride())[1:]
    x0_ix = x0.mul(stride[0]).long()
    x1_ix = x1.mul(stride[0]).long()
    y0_ix = y0.mul(stride[1]).long()
    y1_ix = y1.mul(stride[1]).long()

    input_flat = th_flatten(input)

    vals_00 = input_flat[x0_ix+y0_ix]
    vals_10 = input_flat[x1_ix+y0_ix]
    vals_01 = input_flat[x0_ix+y1_ix]
    vals_11 = input_flat[x1_ix+y1_ix]


    xm1 = 1 - xd
    ym1 = 1 - yd

    x_mapped = (vals_00.mul(xm1).mul(ym1) +
                vals_10.mul(xd).mul(ym1) +
                vals_01.mul(xm1).mul(yd) +
                vals_11.mul(xd).mul(yd))

    return x_mapped.view_as(input)


def th_affine_3d(x, matrix, mode='trilinear', center=True):
    """
    3D Affine image transform on torch.Tensor
    """
    A = matrix[:3,:3]
    b = matrix[:3,3]

    # make a meshgrid of normal coordinates
    coords = th_iterproduct(x.size(1),x.size(2),x.size(3)).float()


    if center:
        # shift the coordinates so center is the origin
        coords[:,0] = coords[:,0] - (x.size(1) / 2. + 0.5)
        coords[:,1] = coords[:,1] - (x.size(2) / 2. + 0.5)
        coords[:,2] = coords[:,2] - (x.size(3) / 2. + 0.5)

    
    # apply the coordinate transformation
    new_coords = coords.mm(A.t().contiguous()) + b.expand_as(coords)

    #print(e-s)
    if center:
        # shift the coordinates back so origin is origin
        new_coords[:,0] = new_coords[:,0] + (x.size(1) / 2. + 0.5)
        new_coords[:,1] = new_coords[:,1] + (x.size(2) / 2. + 0.5)
        new_coords[:,2] = new_coords[:,2] + (x.size(3) / 2. + 0.5)

    # map new coordinates using bilinear interpolation
    if mode == 'nearest':
        x_transformed = th_nearest_interp_3d(x, new_coords)
    elif mode == 'trilinear':
        x_transformed = th_trilinear_interp_3d(x, new_coords)

    return x_transformed


def th_nearest_interp_3d(input, coords):
    """
    2d nearest neighbor interpolation torch.Tensor
    """
    # take clamp of coords so they're in the image bounds
    coords[:,0] = torch.clamp(coords[:,0], 0, input.size(1)-1).round()
    coords[:,1] = torch.clamp(coords[:,1], 0, input.size(2)-1).round()
    coords[:,2] = torch.clamp(coords[:,2], 0, input.size(3)-1).round()

    stride = torch.LongTensor(input.stride())[1:].float()
    idx = coords.mv(stride)

    input_flat = th_flatten(input)

    mapped_vals = input_flat[idx.long()]

    return mapped_vals.view_as(input)



def th_trilinear_interp_3d(input, coords):
    """
    trilinear interpolation of 3D torch.Tensor image
    """
    # take clamp then floor/ceil of x coords
    x = torch.clamp(coords[:,0], 0, input.size(1)-2)
    x0 = x.floor()
    x1 = x0 + 1
    # take clamp then floor/ceil of y coords
    y = torch.clamp(coords[:,1], 0, input.size(2)-2)
    y0 = y.floor()
    y1 = y0 + 1
    # take clamp then floor/ceil of z coords
    z = torch.clamp(coords[:,2], 0, input.size(3)-2)
    z0 = z.floor()
    z1 = z0 + 1

    xd = x - x0
    yd = y - y0
    zd = z - z0

    stride = torch.LongTensor(input.stride())[1:]
    x0_ix = x0.mul(stride[0]).long()
    x1_ix = x1.mul(stride[0]).long()
    y0_ix = y0.mul(stride[1]).long()
    y1_ix = y1.mul(stride[1]).long()
    z0_ix = z0.mul(stride[2]).long()
    z1_ix = z1.mul(stride[2]).long()

    input_flat = th_flatten(input)

    vals_000 = input_flat[x0_ix+y0_ix+z0_ix]
    vals_100 = input_flat[x1_ix+y0_ix+z0_ix]
    vals_010 = input_flat[x0_ix+y1_ix+z0_ix]
    vals_001 = input_flat[x0_ix+y0_ix+z1_ix]
    vals_101 = input_flat[x1_ix+y0_ix+z1_ix]
    vals_011 = input_flat[x0_ix+y1_ix+z1_ix]
    vals_110 = input_flat[x1_ix+y1_ix+z0_ix]
    vals_111 = input_flat[x1_ix+y1_ix+z1_ix]

    xm1 = 1 - xd
    ym1 = 1 - yd
    zm1 = 1 - zd

    x_mapped = (vals_000.mul(xm1).mul(ym1).mul(zm1) +
                vals_100.mul(xd).mul(ym1).mul(zm1) +
                vals_010.mul(xm1).mul(yd).mul(zm1) +
                vals_001.mul(xm1).mul(ym1).mul(zd) +
                vals_101.mul(xd).mul(ym1).mul(zd) +
                vals_011.mul(xm1).mul(yd).mul(zd) +
                vals_110.mul(xd).mul(yd).mul(zm1) +
                vals_111.mul(xd).mul(yd).mul(zd))

    return x_mapped.view_as(input)


def th_pearsonr(x, y):
    """
    mimics scipy.stats.pearsonr
    """
    mean_x = torch.mean(x)
    mean_y = torch.mean(y)
    xm = x.sub(mean_x)
    ym = y.sub(mean_y)
    r_num = xm.dot(ym)
    r_den = torch.norm(xm, 2) * torch.norm(ym, 2)
    r_val = r_num / r_den
    return r_val


def th_corrcoef(x):
    """
    mimics np.corrcoef
    """
    # calculate covariance matrix of rows
    mean_x = torch.mean(x, 1)
    xm = x.sub(mean_x.expand_as(x))
    c = xm.mm(xm.t())
    c = c / (x.size(1) - 1)

    # normalize covariance matrix
    d = torch.diag(c)
    stddev = torch.pow(d, 0.5)
    c = c.div(stddev.expand_as(c))
    c = c.div(stddev.expand_as(c).t())

    # clamp between -1 and 1
    c = torch.clamp(c, -1.0, 1.0)

    return c


def th_matrixcorr(x, y):
    """
    return a correlation matrix between
    columns of x and columns of y.

    So, if X.size() == (1000,4) and Y.size() == (1000,5),
    then the result will be of size (4,5) with the
    (i,j) value equal to the pearsonr correlation coeff
    between column i in X and column j in Y
    """
    mean_x = torch.mean(x, 0)
    mean_y = torch.mean(y, 0)
    xm = x.sub(mean_x.expand_as(x))
    ym = y.sub(mean_y.expand_as(y))
    r_num = xm.t().mm(ym)
    r_den1 = torch.norm(xm,2,0)
    r_den2 = torch.norm(ym,2,0)
    r_den = r_den1.t().mm(r_den2)
    r_mat = r_num.div(r_den)
    return r_mat


def th_random_choice(a, size=None, replace=True, p=None):
    """
    Parameters
    -----------
    a : 1-D array-like
        If a torch.Tensor, a random sample is generated from its elements.
        If an int, the random sample is generated as if a was torch.range(n)
    size : int, optional
        Number of samples to draw. Default is None, in which case a
        single value is returned.
    replace : boolean, optional
        Whether the sample is with or without replacement
    p : 1-D array-like, optional
        The probabilities associated with each entry in a.
        If not given the sample assumes a uniform distribution over all
        entries in a.

    Returns
    --------
    samples : 1-D ndarray, shape (size,)
        The generated random samples
    """
    if size is None:
        size = 1

    if isinstance(a, int):
        a = torch.range(0, a-1)

    if p is None:
        if replace:
            idx = torch.floor(torch.rand(size)*a.size(0)).long()
        else:
            idx = torch.randperm(a.size(0))[:size]
    else:
        if abs(1.0-sum(p)) > 1e-3:
            raise ValueError('p must sum to 1.0')
        if not replace:
            raise ValueError('replace must equal true if probabilities given')
        idx_vec = torch.cat([torch.zeros(round(p[i]*1000))+i for i in range(len(p))])
        idx = (torch.floor(torch.rand(size)*999.99)).long()
        idx = idx_vec[idx].long()
    return a[idx]


def save_transform(file, transform):
    """
    Save a transform object
    """
    with open(file, 'wb') as output_file:
        pickler = pickle.Pickler(output_file, -1)
        pickler.dump(transform)


def load_transform(file):
    """
    Load a transform object
    """
    with open(file, 'rb') as input_file:
        transform = pickle.load(input_file)
    return transform
    


    
