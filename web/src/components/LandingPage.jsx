import { useState } from 'react';
import LoadingLogo from './LoadingLogo';

export default function LandingPage({ onSignIn, onSignUp }) {
  const [mode, setMode] = useState('signin'); // 'signin' or 'signup'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) return;

    setLoading(true);
    try {
      if (mode === 'signin') {
        await onSignIn(email, password);
      } else {
        await onSignUp(email, password);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 overflow-hidden relative">
      {/* Animated background gradient orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 -left-1/4 w-96 h-96 bg-gradient-to-br from-amber-500/20 to-orange-500/20 rounded-full blur-3xl animate-pulse" style={{ animationDuration: '4s' }}></div>
        <div className="absolute bottom-1/4 -right-1/4 w-96 h-96 bg-gradient-to-br from-pink-500/20 to-rose-500/20 rounded-full blur-3xl animate-pulse" style={{ animationDuration: '5s', animationDelay: '1s' }}></div>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-br from-amber-500/10 via-pink-500/10 to-rose-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDuration: '6s', animationDelay: '2s' }}></div>
      </div>

      <div className="relative z-10 w-full max-w-6xl">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Left side - Hero content */}
          <div className="space-y-8 text-center lg:text-left">
            {/* Main heading */}
            <div className="space-y-6 select-none">
              {/* Logo - Bigger and placed at top */}
              <div className="flex justify-center lg:justify-start">
                <div className="animate-float scale-150">
                  <LoadingLogo size="lg" />
                </div>
              </div>

              <h1 className="text-5xl md:text-6xl font-bold leading-tight">
                <span className="bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent animate-gradient">
                  StudySphere
                </span>
              </h1>

              <p className="text-2xl md:text-3xl text-zinc-300 font-semibold">
                Breeze through assignments and prepare for exams, powered completely by AI
              </p>
            </div>
          </div>

          {/* Right side - Auth form */}
          <div className="flex justify-center lg:justify-end">
            <div className="w-full max-w-md">
              <div className="bg-zinc-950 border-2 border-zinc-800/50 rounded-2xl p-8 shadow-2xl backdrop-blur-sm">
                {/* Form header */}
                <div className="text-center mb-6 select-none">
                  <h2 className="text-2xl font-bold bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent mb-2">
                    {mode === 'signin' ? 'Welcome Back' : 'Get Started'}
                  </h2>
                  <p className="text-zinc-500 text-sm">
                    {mode === 'signin' ? 'Sign in to continue your journey' : 'Create your free account'}
                  </p>
                </div>

                {/* Auth form */}
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-zinc-400 mb-2">Email</label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="w-full px-4 py-3 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 transition-all"
                      disabled={loading}
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-zinc-400 mb-2">Password</label>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="********"
                      className="w-full px-4 py-3 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 transition-all"
                      disabled={loading}
                      required
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={loading || !email || !password}
                    className="w-full py-3 rounded-lg font-semibold text-white bg-gradient-to-r from-orange-500 via-amber-500 to-pink-500 hover:from-orange-600 hover:via-amber-600 hover:to-pink-600 disabled:opacity-50 transition-all duration-300 hover:scale-105 active:scale-95 shadow-lg shadow-amber-500/25 flex items-center justify-center gap-2"
                  >
                    {loading ? (
                      <>
                        <LoadingLogo size="sm" />
                        <span>Processing...</span>
                      </>
                    ) : (
                      <span>{mode === 'signin' ? 'Sign In' : 'Create Account'}</span>
                    )}
                  </button>
                </form>

                {/* Toggle mode */}
                <div className="mt-6 text-center select-none">
                  <button
                    onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}
                    disabled={loading}
                    className="text-sm text-zinc-500 hover:text-amber-400 transition-colors disabled:opacity-50"
                  >
                    {mode === 'signin' ? (
                      <>
                        Don't have an account? <span className="font-semibold">Sign up</span>
                      </>
                    ) : (
                      <>
                        Already have an account? <span className="font-semibold">Sign in</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-20px); }
        }

        @keyframes gradient {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }

        .animate-float {
          animation: float 3s ease-in-out infinite;
        }

        .animate-gradient {
          background-size: 200% 200%;
          animation: gradient 4s ease infinite;
        }
      `}</style>
    </div>
  );
}
