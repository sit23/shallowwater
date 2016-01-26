#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Shallow Water Model

- Two dimensional shallow water in a rotating frame
- Staggered Arakawa-C lat:lon grid
- periodic in the x-dimension
- fixed boundary conditions in the y-dimension

h = H + η

∂/∂t[u] - fv = - g ∂/∂x[η]
∂/∂t[v] + fu = - g ∂/∂y[η]
∂/∂t[h] + H(∂/∂x[u] + ∂/∂y[v]) = 0

f = f0 + βy
"""

import numpy as np


import numpy as np

from arakawac import ArakawaCGrid
from timesteppers import adamsbashforthgen


class LinearShallowWater(ArakawaCGrid):
    def __init__(self, nx, ny, Lx=1.0e7, Ly=1.0e7, f0=0.0, beta=2.0e-11, g=9.8, H=10.0, nu=1.0e-5, r=1.0e-5, dt=1000.0):
        super(LinearShallowWater, self).__init__(nx, ny, Lx, Ly)

        # Coriolis terms
        self.f0 = f0
        self.beta = beta

        self.g = g
        self.H = H

        # dissipation and friction
        self.nu = nu
        self.r = r
        self.sponge_ny = ny//7
        self.sponge = np.exp(-np.linspace(0, 5, self.sponge_ny))

        # timestepping
        self.dt = dt
        self.tc = 0  # number of timesteps taken
        self.t = 0.0

        self._stepper = adamsbashforthgen(self.rhs, self.dt)

        self._forcings = []
        self._tracers  = {}

    @property
    def h(self):
        return self.phi

    @property
    def _h(self):
        return self._phi



    def add_forcing(self, fn):
        """Add a forcing term to the model.  Typically used as a decorator:

            sw = PeriodicShallowWater(nx, ny)

            @sw.add_forcing
            def dissipate(swmodel):
                dstate = np.zeros_like(swmodel.state)
                dstate[:] = -swmodel.state*0.001
                return dstate

        Forcing functions should take a single argument for the model object itself,
        and return a state delta the same shape as state.
        """
        self._forcings.append(fn)
        return fn

    def damping(self, var):
        # sponges are active at the top and bottom of the domain by applying Rayleigh friction
        # with exponential decay towards the centre of the domain
        var_sponge = np.zeros_like(var)
        var_sponge[:, :self.sponge_ny] = self.sponge[np.newaxis, :]
        var_sponge[:, -self.sponge_ny:] = self.sponge[::-1][np.newaxis, :]
        return self.r*var_sponge*var

    def rhs(self):
        """Calculate the right hand side of the u, v and h equations."""
        f0, beta, g, H, nu = self.f0, self.beta, self.g, self.H, self.nu

        self.apply_boundary_conditions()
        uu, vv = self.uvatuv()

        # the height equation
        h_rhs = -H*self.divergence() + nu*self.del2(self._h) - self.damping(self.h)

        # the u equation
        dhdx = self.diffx(self._h)[:, 1:-1]
        u_rhs = (f0 + beta*self.uy)*vv - g*dhdx + nu*self.del2(self._u) - self.damping(self.u)

        # the v equation
        dhdy  = self.diffy(self._h)[1:-1, :]
        v_rhs = -(f0 + beta*self.vy)*uu - g*dhdy + nu*self.del2(self._v) - self.damping(self.v)

        dstate = np.array([u_rhs, v_rhs, h_rhs])

        for fn in self._forcings:
            dstate += fn(self)

        return dstate

    def step(self):
        dt, tc = self.dt, self.tc

        newstate = self.state + next(self._stepper)
        self.state = newstate


        self.t  += dt
        self.tc += 1

class PeriodicLinearShallowWater(LinearShallowWater):
    """Shallow Water equations periodic in the x-direction."""
    def __init__(self, nx, ny, Lx=1.0e7, Ly=1.0e7, f0=0.0, beta=2.0e-11, g=9.8, H=10.0, nu=1.0e-5, r=1.0e-5, dt=1000.0):
        super(PeriodicLinearShallowWater, self).__init__(nx, ny, Lx, Ly, f0, beta, g, H, nu, r, dt)

    def apply_boundary_conditions(self):
        # left and right-hand boundaries are the same for u
        self._u[0, :] = self._u[-3, :]
        self._u[1, :] = self._u[-2, :]
        self._u[-1, :] = self._u[2, :]

        self._v[0, :] = self._v[-2, :]
        self._v[-1, :] = self._v[1, :]
        self._phi[0, :] = self._phi[-2, :]
        self._phi[-1, :] = self._phi[1, :]

        fields = self._u, self._v, self._phi
        # top and bottom boundaries: zero deriv and damping
        for field in fields:
            field[:, 0] = field[:, 1]
            field[:, -1] = field[:, -2]
            self._fix_boundary_corners(field)



if __name__ == '__main__':

    nx = 128
    ny = 129
    beta=2.0e-11
    Lx = 1.0e7
    Ly = 1.0e7

    ocean = PeriodicLinearShallowWater(nx, ny, Lx, Ly, beta=beta, f0=0.0, g=0.1, H=100.0, dt=3000, nu=1000.0)
    #ocean.h[10:20, 60:80] = 1.0
    #ocean.h[-20:-10] = 1.0
    d = 25
    ocean.h[10:10+2*d, ny//2-d:ny//2+d] = (np.sin(np.linspace(0, np.pi, 2*d))**2)[np.newaxis, :] * (np.sin(np.linspace(0, np.pi, 2*d))**2)[:, np.newaxis]
    #ocean.h[100:100+2*d, ny//2-d:ny//2+d] = (np.sin(np.linspace(0, np.pi, 2*d))**2)[np.newaxis, :] * (np.sin(np.linspace(0, np.pi, 2*d))**2)[:, np.newaxis]
    import matplotlib.pyplot as plt

    plt.ion()

    num_levels = 24
    colorlevels = np.concatenate([np.linspace(-1, -.05, num_levels//2), np.linspace(.05, 1, num_levels//2)])

    ts = []
    es = []
    plt.show()
    for i in range(10000):
        ocean.step()
        if i % 10 == 0:
            plt.figure(1)
            plt.clf()
            #plt.plot(ocean.h[:,0])
            #plt.plot(ocean.h[:,64])
            #plt.ylim(-1,1)
            plt.contourf(ocean.h.T, cmap=plt.cm.RdBu, levels=colorlevels)

            plt.figure(2)
            plt.clf()
            plt.plot(ocean.h[:,0])
            plt.plot(ocean.h[:,48])
            plt.plot(ocean.h[:,64])
            plt.ylim(-1,1)

            plt.figure(3)
            plt.clf()
            energy = np.sum(ocean.g*ocean.h) + np.sum(ocean.u**2) + np.sum(ocean.v**2)
            ts.append(ocean.t)
            es.append(energy)
            plt.plot(ts, es)

            plt.pause(0.01)
            plt.draw()