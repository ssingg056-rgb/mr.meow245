import discord
from discord.ext import commands
from constants import ALLOWED_GUILD_IDS, EMBED_COLOR


CATEGORIES = {
    "ai": {
        "label": "🤖 AI Chat",
        "description": "Chat with Mr. Meow AI",
    },
    "economy": {
        "label": "💰 Economy",
        "description": "Virtual currency commands",
    },
    "owner": {
        "label": "👑 Owner",
        "description": "Owner-only commands",
    },
}


class HelpSelect(discord.ui.Select):
    def __init__(self, cog):
        options = [
            discord.SelectOption(
                label=data["label"],
                description=data["description"],
                value=key,
            )
            for key, data in CATEGORIES.items()
        ]
        super().__init__(placeholder="Choose a command category...", options=options, min_values=1, max_values=1)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        embed = self.cog._build_embed(self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=120)
        self.cog = cog
        self.add_item(HelpSelect(cog))


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _build_embed(self, category: str) -> discord.Embed:
        embed = discord.Embed(
            title="🐱 Mr. Meow Help Center",
            color=EMBED_COLOR,
        )

        if category == "ai":
            embed.description = "**AI Chat commands:**"
            embed.add_field(name="`mr.meow <text>`", value="Chat with Mr. Meow AI.", inline=False)
            embed.add_field(name="`<reply to Mr. Meow>`", value="Reply to any Mr. Meow message to continue the conversation.", inline=False)
            embed.add_field(name="`?help`", value="Shows this help menu.", inline=False)

        elif category == "economy":
            embed.description = "**Economy commands:**" 
            embed.add_field(name="`?balance`", value="Check your current coin balance.", inline=False)
            embed.add_field(name="`?daily`", value="Claim your daily coins (24h cooldown).", inline=False)
            embed.add_field(name="`?weekly`", value="Claim your weekly coins (7d cooldown).", inline=False)
            embed.add_field(name="`?send <@user> <amount>`", value="Transfer coins to another user.", inline=False)
            embed.add_field(name="`?gamble <amount>`", value="50/50 chance to double or lose your bet.", inline=False)
            embed.add_field(name="`?leaderboard [page]`", value="Top 10 richest users. Page defaults to 1.", inline=False)
            embed.add_field(name="`?shop`", value="Browse the server shop.", inline=False)
            embed.add_field(name="`?buy <item> [qty]`", value="Purchase an item from the shop.", inline=False)

        elif category == "owner":
            embed.description = "**Owner-only commands:**"
            embed.add_field(name="`mr.meow send <channel/user ID> <text>`", value="Send a message as Mr. Meow to any channel or user.", inline=False)

        embed.set_footer(text="Programmed exclusively by Certified Chad")
        return embed

    @commands.command(name="help")
    async def help_command(self, ctx):
        if ALLOWED_GUILD_IDS and (ctx.guild is None or ctx.guild.id not in ALLOWED_GUILD_IDS):
            return
        embed = self._build_embed("ai")
        await ctx.send(embed=embed, view=HelpView(self))


async def setup(bot):
    await bot.add_cog(HelpCog(bot))