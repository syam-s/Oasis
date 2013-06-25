__author__ = "Mikael Mortensen <mikaem@math.uio.no>"
__date__ = "2013-06-25"
__copyright__ = "Copyright (C) 2013 " + __author__
__license__  = "GNU Lesser GPL version 3 or any later version"

from Oasis import *
from fenicstools import StructuredGrid, ChannelGrid
from numpy import arctan, array, cos, pi
import random
import time

# Create a mesh here
Lx = 2.*pi
Ly = 2.
Lz = pi
Nx = 25
Ny = 19
Nz = 19

mesh = BoxMesh(0., -Ly/2., -Lz/2., Lx, Ly/2., Lz/2., Nx, Ny, Nz)
# Create stretched mesh in y-direction
x = mesh.coordinates() 
x[:, 1] = cos(pi*(x[:, 1]-1.) / 2.)  
u_components = ['u0', 'u1', 'u2']
sys_comp =  u_components + ['p']

class PeriodicDomain(SubDomain):

    def inside(self, x, on_boundary):
        # return True if on left or bottom boundary AND NOT on one of the two slave edges
        #return bool((near(x[0], 0) or near(x[2], -Lz/2.)) and 
                #(not ((near(x[0], Lx) and near(x[2], -Lz/2.)) or 
                      #(near(x[0], 0) and near(x[2], Lz/2.)))) and on_boundary)
        return bool((near(x[0], 0) or near(x[2], -Lz/2.)) and 
                (not (near(x[0], Lx) or near(x[2], Lz/2.))) and on_boundary)
                      
    def map(self, x, y):
        if near(x[0], Lx) and near(x[2], Lz/2.):
            y[0] = x[0] - Lx
            y[1] = x[1] 
            y[2] = x[2] - Lz
        elif near(x[0], Lx):
            y[0] = x[0] - Lx
            y[1] = x[1]
            y[2] = x[2]
        elif near(x[2], Lz/2.):
            y[0] = x[0]
            y[1] = x[1]
            y[2] = x[2] - Lz
        else:
            y[0] = -1000
            y[1] = -1000
            y[2] = -1000
            
constrained_domain = PeriodicDomain()

# Override some problem specific parameters and put the variables in DC_dict
T = 1.
dt = 0.05
folder = "channel_results"
newfolder = create_initial_folders(folder, dt)
statsfolder = path.join(newfolder, "Stats")
h5folder = path.join(newfolder, "HDF5")
update_statistics = 10
check_save_h5 = 10
NS_parameters.update(dict(
    nu = 2.e-5,
    Re_tau = 395.,
    T = T,
    dt = dt,
    folder = folder,
    newfolder = newfolder,
    sys_comp = sys_comp,
    use_krylov_solvers = True,
    use_lumping_of_mass_matrix = False
  )
)
if NS_parameters['velocity_degree'] > 1:
    NS_parameters['use_lumping_of_mass_matrix'] = False

# Put all the NS_parameters in the global namespace of Problem
# These parameters are all imported by the Navier Stokes solver
globals().update(NS_parameters)

# Specify body force
utau = nu * Re_tau
f = Constant((utau**2, 0., 0.))

# Normalize pressure or not? 
#normalize = False

def pre_solve(NS_dict):    
    """Called prior to time loop"""
    globals().update(NS_dict)
    uv = Function(Vv) 
    velocity_plotter = VTKPlotter(uv)
    pressure_plotter = VTKPlotter(p_) 
    globals().update(uv=uv, 
                   velocity_plotter=velocity_plotter,
                   pressure_plotter=pressure_plotter)

# Specify boundary conditions
def create_bcs():
    
    bcs = dict((ui, []) for ui in sys_comp)
    
    def inlet(x, on_bnd):
        return on_bnd and near(x[0], 0)

    def walls(x, on_bnd):
        return on_bnd and (near(x[1], -Ly/2.) or near(x[1], Ly/2.))

    Inlet = AutoSubDomain(inlet)
    facets = FacetFunction('size_t', mesh)
    facets.set_all(0)
    Inlet.mark(facets, 1)    

    bc = [DirichletBC(V, Constant(0), walls)]
    bcs['u0'] = bc
    bcs['u1'] = bc
    bcs['u2'] = bc
    bcs['p'] = []

    for ui in u_components:
        [bc.apply(q_[ui].vector()) for bc in bcs[ui]]
        [bc.apply(q_1[ui].vector()) for bc in bcs[ui]]
        [bc.apply(q_2[ui].vector()) for bc in bcs[ui]]
    
    return bcs

class RandomStreamVector(Expression):
    def __init__(self):
        random.seed(2 + MPI.process_number())
    def eval(self, values, x):
        values[0] = 0.0005*random.random()
        values[1] = 0.0005*random.random()
        values[2] = 0.0005*random.random()
    def value_shape(self):
        return (3,)  
    
def initialize(NS_dict):
    globals().update(NS_dict)
    global voluviz, stats 
    tol = 1e-8
    voluviz = StructuredGrid(V, [Nx, Ny, Nz], [tol, -Ly/2.+tol, -Lz/2.+tol], [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], [Lx-2*tol, Ly-2*tol, Lz-2*tol], statistics=False)
    stats = ChannelGrid(V, [Nx/5, Ny, Nz/5], [tol, -Ly/2.+tol, -Lz/2.+tol], [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], [Lx-2*tol, Ly-2*tol, Lz-2*tol], statistics=True)
    if restart_folder == None:
        psi = interpolate(RandomStreamVector(), Vv)
        u0 = project(curl(psi), Vv)
        u0x = project(u0[0], V)
        u1x = project(u0[1], V)
        u2x = project(u0[2], V)
        y = interpolate(Expression("x[1] > 0 ? 1-x[1] : 1+x[1]"), V)
        uu = project(1.25*(utau/0.41*ln(conditional(y<1e-12, 1.e-12, y)*utau/nu)+5.*utau), V)
        q_['u0'].vector()[:] = uu.vector()[:] 
        q_['u0'].vector().axpy(1.0, u0x.vector())
        q_['u1'].vector()[:] = u1x.vector()[:]
        q_['u2'].vector()[:] = u2x.vector()[:]
        q_1['u0'].vector()[:] = q_['u0'].vector()[:]
        q_2['u0'].vector()[:] = q_['u0'].vector()[:]
        q_1['u1'].vector()[:] = q_['u1'].vector()[:]
        q_2['u1'].vector()[:] = q_['u1'].vector()[:]
        q_1['u2'].vector()[:] = q_['u2'].vector()[:]
        q_2['u2'].vector()[:] = q_['u2'].vector()[:]

# Set up linear solvers
def get_solvers():
    """return three solvers, velocity, pressure and velocity update.
    In case of lumping return None for velocity update"""
    if use_krylov_solvers:
        u_sol = KrylovSolver('bicgstab', 'jacobi')
        u_sol.parameters['error_on_nonconvergence'] = False
        u_sol.parameters['nonzero_initial_guess'] = True
        u_sol.parameters['preconditioner']['reuse'] = False
        u_sol.parameters['monitor_convergence'] = True
        u_sol.parameters['maximum_iterations'] = 100
        u_sol.parameters['relative_tolerance'] = 1e-8
        u_sol.parameters['absolute_tolerance'] = 1e-8
        u_sol.t = 0

        if use_lumping_of_mass_matrix:
            du_sol = None
        else:
            du_sol = KrylovSolver('bicgstab', 'hypre_euclid')
            du_sol.parameters['error_on_nonconvergence'] = False
            du_sol.parameters['nonzero_initial_guess'] = True
            du_sol.parameters['preconditioner']['reuse'] = True
            du_sol.parameters['monitor_convergence'] = True
            du_sol.parameters['maximum_iterations'] = 50
            du_sol.parameters['relative_tolerance'] = 1e-9
            du_sol.parameters['absolute_tolerance'] = 1e-10
            du_sol.t = 0
            
        p_sol = KrylovSolver('gmres', 'hypre_amg')
        p_sol.parameters['error_on_nonconvergence'] = True
        p_sol.parameters['nonzero_initial_guess'] = True
        p_sol.parameters['preconditioner']['reuse'] = True
        p_sol.parameters['monitor_convergence'] = True
        p_sol.parameters['maximum_iterations'] = 100
        p_sol.parameters['relative_tolerance'] = 1e-8
        p_sol.parameters['absolute_tolerance'] = 1e-8
        p_sol.t = 0
    else:
        u_sol = LUSolver()
        u_sol.t = 0

        if use_lumping_of_mass_matrix:
            du_sol = None
        else:
            du_sol = LUSolver()
            du_sol.parameters['reuse_factorization'] = True
            du_sol.t = 0

        p_sol = LUSolver()
        p_sol.parameters['reuse_factorization'] = True
        p_sol.t = 0
        
    return u_sol, p_sol, du_sol
    
def pre_pressure_solve():
    pass

def pre_velocity_tentative_solve(ui):
    if use_krylov_solvers:
        if ui == "u0":
            u_sol.parameters['preconditioner']['reuse'] = False
            u_sol.parameters['relative_tolerance'] = 1e-9
            u_sol.parameters['absolute_tolerance'] = 1e-9
        else:
            u_sol.parameters['preconditioner']['reuse'] = True
            u_sol.parameters['relative_tolerance'] = 1e-8
            u_sol.parameters['absolute_tolerance'] = 1e-8

def update_end_of_timestep(tstep):    
            
    if tstep % update_statistics == 0:
        stats(q_['u0'], q_['u1'], q_['u2'])
        
    if tstep % check_save_h5 == 0:
        stats.toh5(0, tstep, filename=statsfolder+"/dump_mean_{}.h5".format(tstep))
        voluviz(q_['u0'])
        voluviz.toh5(0, tstep, filename=h5folder+"/snapshot_u0_{}.h5".format(tstep))
        voluviz.probes.clear()
        voluviz(q_['u1'])
        voluviz.toh5(0, tstep, filename=h5folder+"/snapshot_u1_{}.h5".format(tstep))
        voluviz.probes.clear()
        voluviz(q_['u2'])
        voluviz.toh5(0, tstep, filename=h5folder+"/snapshot_u2_{}.h5".format(tstep))
        voluviz.probes.clear()
        enstrophy = project(0.5*dot(curl(u_), curl(u_)), V)
        voluviz(enstrophy)
        voluviz.toh5(0, tstep, filename=h5folder+"/snapshot_enstrophy_{}.h5".format(tstep))
        voluviz.probes.clear()
        enstrophy = project(0.5*QC(u_), V)
        voluviz(enstrophy)
        voluviz.toh5(0, tstep, filename=h5folder+"/snapshot_Q_{}.h5".format(tstep))
        voluviz.probes.clear()
        
        uv.assign(project(u_, Vv))
        pressure_plotter.plot()
        velocity_plotter.plot()
    
def theend():
    pass
