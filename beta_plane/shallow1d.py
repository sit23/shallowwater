
import numpy as np

from arakawac import Arakawa1D
from timesteppers import adamsbashforthgen


class ShallowWater1D(Arakawa1D):
    """The Shallow Water Equations on the Arakawa-C grid."""
    def __init__(self, nx, Lx=1.0e7, nu=1.0e3, nu_phi=None, dt=1000.0):
        super(ShallowWater1D, self).__init__(nx, Lx)

        # dissipation and friction
        self.nu = nu                                    # u, v dissipation
        self.nu_phi = nu if nu_phi is None else nu_phi  # phi dissipation

        # timestepping
        self.dt = dt
        self.tc = 0  # number of timesteps taken
        self.t = 0.0

        self._stepper = adamsbashforthgen(self._rhs, self.dt)

        self.forcings = []
        self._tracers  = {}

    def add_forcing(self, fn):
        """Add a forcing term to the model.  Typically used as a decorator:

            @sw.add_forcing
            def dissipate(swmodel):
                dstate = np.zeros_like(swmodel.state)
                dstate[:] = -swmodel.state*0.001
                return dstate

        Forcing functions should take a single argument for the model object itself,
        and return a state delta the same shape as state.
        """
        self.forcings.append(fn)
        return fn

    def rhs(self):
        """Set a right-hand side term for the equation.
        Default is [0,0], override this method when subclassing."""
        zeros = np.zeros_like(self.state)
        return zeros

    def _dynamics_terms(self):
        """Calculate the dynamics for the u, v and phi equations."""
        # ~~~ Nonlinear Dynamics ~~~
        ubarx = self.x_average(self._u)

        # the height equation
        phi_at_u = self.x_average(self._phi)  # (nx+1)
        phi_rhs  = - self.diffx(phi_at_u * self.u)       # (nx) nonlinear
        #phi_rhs  = - self.diffx(np.mean(phi_at_u) * self.u)       # (nx) linear
        phi_rhs += self.nu_phi*self.diff2x(self._phi)    # (nx) diffusion

        # the u equation
        dhdx = self.diffx(self._phi)         # (nx+2)
        ududx = 0.5*self.diffx(ubarx**2)     # u*du/dx at u points

        u_rhs  = -dhdx
        u_rhs += self.nu*self.diff2x(self._u)
        #u_rhs += - ududx                     # nonlin u advection terms

        dstate = np.array([u_rhs, phi_rhs])
        return dstate

    def _rhs(self):
        dstate = np.zeros_like(self.state)
        for f in self.forcings:
            dstate += f(self)
        return self._dynamics_terms() + self.rhs() + dstate

    def step(self):
        dt, tc = self.dt, self.tc

        self._apply_boundary_conditions()
        newstate = self.state + next(self._stepper)
        self.state = newstate

        self.t  += dt
        self.tc += 1

class LinearShallowWater1D(ShallowWater1D):
    def __init__(self, nx, Lx=1.0e7, H=100., nu=1.0e3, nu_phi=None, dt=1000.0):
        super(LinearShallowWater1D, self).__init__(nx, Lx=Lx, nu=nu, nu_phi=nu_phi, dt=dt)
        self.H = H

    def _dynamics_terms(self):
        """Calculate the dynamics for the u, v and phi equations."""
        # ~~~ Linear Dynamics ~~~
        ubarx = self.x_average(self._u)

        # the height equation
        phi_rhs  = - self.H*self.diffx(self.u)       # (nx) linear
        phi_rhs += self.nu_phi*self.diff2x(self._phi)    # (nx) diffusion

        # the u equation
        dhdx = self.diffx(self._phi)         # (nx+2)
        u_rhs  = -dhdx
        u_rhs += self.nu*self.diff2x(self._u)

        dstate = np.array([u_rhs, phi_rhs])
        return dstate


if __name__ == '__main__':
    import matplotlib.pyplot as plt

    H = 2.
    s = 1.
    nx = 128
    Lx = 2*np.pi
    xi_ref_frame = False

    sw = LinearShallowWater1D(nx, Lx, H=H, nu=3e-3, dt=.01)

    # #### forcings ####
    def exoplanet_diurnal_cycle(t):
        phi_eq = np.exp(1j*(sw.phix - s*t))
        phi_eq[phi_eq < 0] = 0.0
        return phi_eq*0.1*H

    def diurnal_forcing(sw):
        t_rad = 10.0
        t_fric = 10.0

        # rayleigh friction
        du = np.zeros_like(sw.u)
        du = -sw.u/t_fric

        # newtonian cooling
        dphi = np.zeros_like(sw.phi)
        ss = exoplanet_diurnal_cycle(sw.t)
        dphi[:] = (ss - sw.phi) / t_rad
        return np.array([du, dphi])


    # #### initial state ####
    # sw.phi[:] = 0  # this is the default
    sw.phi[:] += np.exp(-((1.0-sw.phix)/.3)**2)  # gaussian blob centred at 1.0
    #sw.add_forcing(diurnal_forcing)

    plt.ion()
    plt.show()
    for i in range(10000):
        sw.step()
        if i % 20 == 0:
            print('[t={:7.2f} h range [{:.2f}, {:.2f}]'.format(sw.t/86400, sw.phi.min(), sw.phi.max()))
            plt.figure(1)
            plt.clf()

            peq = exoplanet_diurnal_cycle(sw.t)

            if xi_ref_frame:
                rollx = np.argmax(peq)
                plt.plot(sw.phix, np.roll(sw.phi, -rollx+nx//2))
                if diurnal_forcing in sw.forcings:
                    plt.plot(sw.phix, np.roll(peq, -rollx+nx//2))
            else:
                # plot in the x reference frame
                plt.plot(sw.phix, sw.phi)
                if diurnal_forcing in sw.forcings:
                    plt.plot(sw.phix, peq)

            plt.ylim(-1, 1)
            plt.xlim(-Lx/2, Lx/2)
            plt.pause(0.01)
            plt.draw()
