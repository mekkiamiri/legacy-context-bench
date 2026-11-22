package com.ex.web;

import com.ex.service.UserService;
import com.ex.service.UserServiceImpl;

/**
 * Connexion d'un utilisateur : vérifie le mot de passe.
 */
public class LoginAction extends BaseAction {
    private UserService userService = new UserServiceImpl();
    private String userName;
    private String password;

    @Override
    public String execute() {
        if (!userService.authenticate(userName, password)) {
            addError("login.failed"); // { accolade dans un commentaire
            return "input";
        }
        String s = "chaîne avec } accolade";
        return super.execute();
    }
}
