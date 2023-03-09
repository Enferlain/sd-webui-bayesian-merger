from pathlib import Path

from bayes_opt import BayesianOptimization
from bayes_opt.logger import JSONLogger
from bayes_opt.event import Events

from sd_webui_bayesian_merger.generator import Generator
from sd_webui_bayesian_merger.prompter import Prompter
from sd_webui_bayesian_merger.merger import Merger
from sd_webui_bayesian_merger.scorer import Scorer


class BayesianOptimiser:
    def __init__(
        self,
        url,
        batch_size,
        model_a,
        model_b,
        device,
        payloads_dir,
        wildcards_dir,
        scorer_model_dir,
        init_points,
        n_iters,
    ):
        self.generator = Generator(url, batch_size)
        self.merger = Merger(model_a, model_b, device)
        self.scorer = Scorer(scorer_model_dir, device)
        self.prompter = Prompter(payloads_dir, wildcards_dir)
        self.init_points = init_points
        self.n_iters = n_iters
        self.start_logging()

    def start_logging(self):
        log_path = Path("logs", f'{self.merger.output_file.stem}.json')
        self.logger = JSONLogger(path=str(log_path))

    def sd_target_function(self, **params):
        # TODO: in args?
        # skip_position_ids = 0

        weights = [params[f"block_{i}"] for i in range(25)]
        base_alpha = params["base_alpha"]

        self.merger.merge(
            weights,
            base_alpha,
        )

        # TODO: is this forcing the model load despite the same name?
        self.generator.switch_model(self.merger.model_out_name)

        # generate images
        images = []
        for payload in self.prompter.render_payloads():
            images.extend(self.generator.batch_generate(payload))

        # score images
        scores = self.scorer.batch_score(images)

        # spit out a single value for optimisation
        return self.scorer.average_score(scores)

    def optimise(self) -> None:
        # TODO: what if we want to optimise only certain blocks?
        pbounds = {f"block_{i}": (0.0, 1.0) for i in range(25)}
        pbounds["base_alpha"] = (0.0, 1.0)

        # TODO: fork bayesian-optimisation and add LHS
        self.optimizer = BayesianOptimization(
            f=self.sd_target_function,
            pbounds=pbounds,
            random_state=1,
        )

        self.optimizer.subscribe(Events.OPTIMIZATION_STEP, self.logger)

        self.optimizer.maximize(
            init_points=self.init_points,
            n_iter=self.n_iters,
        )

    def postprocess(self) -> None:
        for i, res in enumerate(self.optimizer.res):
            print(f"Iteration {i}: \n\t{res}")

        print(self.optimizer.max)
