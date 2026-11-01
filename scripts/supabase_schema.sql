-- Supabase project schema (run once in the Supabase SQL editor, not by scripts/migrate.py).
-- Safe to re-run: every statement is idempotent.

-- Create the watchlists table
CREATE TABLE IF NOT EXISTS public.watchlists (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    symbol TEXT NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, symbol) -- Prevent duplicate symbols for the same user
);

-- Enable Row Level Security (RLS)
ALTER TABLE public.watchlists ENABLE ROW LEVEL SECURITY;

-- Users can only SELECT, INSERT and DELETE their own watchlist rows
DROP POLICY IF EXISTS "Users can view their own watchlist" ON public.watchlists;
CREATE POLICY "Users can view their own watchlist"
ON public.watchlists FOR SELECT
USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert into their own watchlist" ON public.watchlists;
CREATE POLICY "Users can insert into their own watchlist"
ON public.watchlists FOR INSERT
WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can delete from their own watchlist" ON public.watchlists;
CREATE POLICY "Users can delete from their own watchlist"
ON public.watchlists FOR DELETE
USING ((SELECT auth.uid()) = user_id);

-- Create public.users table for profile data
CREATE TABLE IF NOT EXISTS public.users (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS on users table
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Users can read their own profile
DROP POLICY IF EXISTS "Users can view own profile" ON public.users;
CREATE POLICY "Users can view own profile"
ON public.users FOR SELECT
USING ((SELECT auth.uid()) = id);

-- Users can create their own profile row (the dashboard saves profiles with upsert,
-- which needs INSERT as well as UPDATE permission)
DROP POLICY IF EXISTS "Users can insert own profile" ON public.users;
CREATE POLICY "Users can insert own profile"
ON public.users FOR INSERT
WITH CHECK ((SELECT auth.uid()) = id);

-- Users can update their own profile
DROP POLICY IF EXISTS "Users can update own profile" ON public.users;
CREATE POLICY "Users can update own profile"
ON public.users FOR UPDATE
USING ((SELECT auth.uid()) = id)
WITH CHECK ((SELECT auth.uid()) = id);

-- Function to handle new user signup. SECURITY DEFINER runs as the owner, so pin the
-- search_path and qualify every name.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.users (id, email, full_name, avatar_url)
    VALUES (
        new.id,
        new.email,
        new.raw_user_meta_data->>'full_name',
        new.raw_user_meta_data->>'avatar_url'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN new;
END;
$$;

-- Trigger to call function on signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
